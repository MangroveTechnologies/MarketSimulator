"""Experiment executor service.

Manages experiment lifecycle: validate, launch (generate plan + enqueue
RQ jobs), pause (signal workers to stop), resume (re-enqueue remaining work),
and status queries.

Experiment configs are stored as config.json in the experiment directory.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Any

import redis as redis_lib

from experiment_server.config import settings
from experiment_server.models.experiment import ExperimentConfig
from experiment_server.services.dataset import compute_file_hash, discover_datasets
from experiment_server.services.plan_generator import RunSpec, compute_total_runs, generate_plan
from experiment_server.services.query import count_completed


def _experiments_dir() -> str:
    return os.path.join(settings.data_dir, "experiments")


def _experiment_dir(experiment_id: str) -> str:
    return os.path.join(_experiments_dir(), experiment_id)


def _config_path(experiment_id: str) -> str:
    return os.path.join(_experiment_dir(experiment_id), "config.json")


def _get_code_version() -> str:
    """Auto-detect git SHA. Returns empty string if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_experiment(config: ExperimentConfig) -> ExperimentConfig:
    """Create a new experiment in draft status.

    Generates an experiment_id, creates the directory, and saves config.json.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    experiment_id = f"exp_{timestamp}"

    config.experiment_id = experiment_id
    config.status = "draft"
    config.created_at = datetime.now(timezone.utc).isoformat()

    if not config.code_version:
        config.code_version = _get_code_version()

    exp_dir = _experiment_dir(experiment_id)
    os.makedirs(exp_dir, exist_ok=True)

    _save_config(config)
    return config


def get_experiment(experiment_id: str) -> ExperimentConfig | None:
    """Load an experiment config from disk."""
    path = _config_path(experiment_id)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    return ExperimentConfig(**data)


def list_experiments() -> list[ExperimentConfig]:
    """List all experiments sorted by creation date (newest first)."""
    exp_dir = _experiments_dir()
    if not os.path.isdir(exp_dir):
        return []

    results = []
    for name in sorted(os.listdir(exp_dir), reverse=True):
        config_path = os.path.join(exp_dir, name, "config.json")
        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    data = json.load(f)
                results.append(ExperimentConfig(**data))
            except Exception:
                continue
    return results


def update_experiment(experiment_id: str, config: ExperimentConfig) -> ExperimentConfig:
    """Update a draft experiment's config."""
    existing = get_experiment(experiment_id)
    if not existing:
        raise ValueError(f"Experiment {experiment_id} not found")
    if existing.status != "draft":
        raise ValueError(f"Cannot update experiment in {existing.status} status")

    config.experiment_id = experiment_id
    config.status = "draft"
    config.created_at = existing.created_at
    _save_config(config)
    return config


def delete_experiment(experiment_id: str) -> None:
    """Delete an experiment directory (draft or completed only)."""
    config = get_experiment(experiment_id)
    if config and config.status == "running":
        raise ValueError("Cannot delete a running experiment")

    import shutil
    exp_dir = _experiment_dir(experiment_id)
    if os.path.isdir(exp_dir):
        shutil.rmtree(exp_dir)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def validate_experiment(experiment_id: str) -> dict[str, Any]:
    """Validate an experiment config and compute the run count.

    Returns {valid: bool, total_runs: int, errors: [], warnings: []}.
    """
    config = get_experiment(experiment_id)
    if not config:
        return {"valid": False, "total_runs": 0,
                "errors": ["Experiment not found"], "warnings": []}

    errs = []
    warns = []

    if not config.datasets:
        errs.append("No datasets selected")

    if config.search_mode == "grid":
        if not config.entry_signals.triggers:
            errs.append("No entry trigger signals selected")
        if not config.entry_signals.filters:
            errs.append("No entry filter signals selected")
    elif config.search_mode == "random":
        if not config.n_random:
            errs.append("Random search mode requires n_random > 0")

    # Compute total runs
    total = 0
    if not errs:
        try:
            total = compute_total_runs(config)
        except Exception as e:
            errs.append(f"Failed to compute run count: {e}")

    if total == 0 and not errs:
        errs.append("Parameter space produces 0 valid runs (constraints may be too restrictive)")

    valid = len(errs) == 0

    if valid:
        config.status = "validated"
        config.total_runs = total
        _save_config(config)

    return {
        "valid": valid,
        "total_runs": total,
        "errors": errs,
        "warnings": warns,
    }


def launch_experiment(
    experiment_id: str,
    redis_url: str | None = None,
    enqueue_fn: Any = None,
) -> dict[str, Any]:
    """Launch an experiment: generate plan, compute hashes, enqueue workers.

    Args:
        experiment_id: The experiment to launch.
        redis_url: Redis URL for job queue. None to skip queuing (testing).
        enqueue_fn: Optional callable for testing (replaces RQ enqueue).

    Returns:
        {status, workers, total_runs}.
    """
    config = get_experiment(experiment_id)
    if not config:
        raise ValueError(f"Experiment {experiment_id} not found")
    if config.status not in ("validated", "paused"):
        raise ValueError(f"Experiment must be validated before launch (status: {config.status})")

    # Compute data file hashes and row counts
    for ds in config.datasets:
        file_path = os.path.join(settings.ohlcv_dir, ds.file)
        if os.path.exists(file_path):
            if not ds.hash:
                ds.hash = compute_file_hash(file_path)
            if not ds.rows:
                with open(file_path) as f:
                    ds.rows = max(0, sum(1 for _ in f) - 1)

    # Generate the deterministic plan
    plan = generate_plan(config)

    # Split plan by dataset for worker assignment
    dataset_runs: dict[str, list[RunSpec]] = {}
    for run in plan:
        dataset_runs.setdefault(run.dataset_key, []).append(run)

    # Create worker jobs (round-robin split within each dataset)
    workers_per_ds = config.workers_per_dataset
    jobs = []
    worker_id = 0

    for dataset_key, runs in dataset_runs.items():
        splits: list[list[RunSpec]] = [[] for _ in range(workers_per_ds)]
        for i, run in enumerate(runs):
            splits[i % workers_per_ds].append(run)

        for split in splits:
            if split:
                jobs.append({
                    "experiment_id": experiment_id,
                    "experiment_dir": _experiment_dir(experiment_id),
                    "dataset_key": dataset_key,
                    "worker_id": worker_id,
                    "runs": [r.__dict__ for r in split],
                    "experiment_config": config.model_dump(),
                    "experiment_seed": config.seed,
                    "code_version": config.code_version,
                    "chunk_size": settings.chunk_size,
                    "redis_url": redis_url or settings.redis_url,
                })
                worker_id += 1

    # Enqueue/launch jobs
    if enqueue_fn:
        for job in jobs:
            enqueue_fn(job)
    else:
        # Launch workers directly via multiprocessing (no Redis required)
        import multiprocessing
        from experiment_server.workers.sweep_worker import execute_sweep_job

        def _run_worker(job_kwargs):
            try:
                execute_sweep_job(**job_kwargs)
            except Exception as e:
                import traceback
                traceback.print_exc()

        for job in jobs:
            p = multiprocessing.Process(
                target=_run_worker,
                args=(job,),
                name=f"worker-{job['worker_id']}-{job['dataset_key']}",
                daemon=True,
            )
            p.start()

    # Update status
    config.status = "running"
    config.total_runs = len(plan)
    _save_config(config)

    return {
        "status": "running",
        "workers": worker_id,
        "total_runs": len(plan),
    }


def pause_experiment(experiment_id: str, redis_url: str | None = None) -> None:
    """Pause a running experiment by setting a stop signal in Redis."""
    config = get_experiment(experiment_id)
    if not config or config.status != "running":
        raise ValueError("Experiment is not running")

    if redis_url:
        r = redis_lib.from_url(redis_url)
        r.set(f"exp:{experiment_id}:pause", "1")

    config.status = "paused"
    _save_config(config)


def get_experiment_progress(experiment_id: str) -> dict[str, Any]:
    """Get current progress by counting completed Parquet rows."""
    config = get_experiment(experiment_id)
    if not config:
        return {}

    exp_dir = _experiment_dir(experiment_id)
    completed_indices = count_completed(exp_dir)

    return {
        "experiment_id": experiment_id,
        "status": config.status,
        "total_runs": config.total_runs or 0,
        "completed": len(completed_indices),
    }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _save_config(config: ExperimentConfig) -> None:
    """Save experiment config to config.json."""
    path = _config_path(config.experiment_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(config.model_dump(), f, indent=2, default=str)
