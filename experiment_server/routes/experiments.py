"""Experiment CRUD and lifecycle API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from experiment_server.models.experiment import ExperimentConfig
from experiment_server.services import executor

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", status_code=201)
async def create_experiment(config: ExperimentConfig) -> dict[str, Any]:
    """Create a new experiment in draft status."""
    result = executor.create_experiment(config)
    return {
        "experiment_id": result.experiment_id,
        "status": result.status,
        "created_at": result.created_at,
    }


@router.get("")
async def list_experiments() -> list[dict[str, Any]]:
    """List all experiments."""
    experiments = executor.list_experiments()
    return [
        {
            "experiment_id": e.experiment_id,
            "name": e.name,
            "status": e.status,
            "total_runs": e.total_runs,
            "search_mode": e.search_mode,
            "created_at": e.created_at,
        }
        for e in experiments
    ]


@router.get("/{experiment_id}")
async def get_experiment(experiment_id: str) -> dict[str, Any]:
    """Get experiment detail including full config."""
    config = executor.get_experiment(experiment_id)
    if not config:
        raise HTTPException(status_code=404, detail="Experiment not found")

    progress = executor.get_experiment_progress(experiment_id)
    result = config.model_dump()
    result["completed_runs"] = progress.get("completed", 0)
    return result


@router.put("/{experiment_id}")
async def update_experiment(
    experiment_id: str, config: ExperimentConfig,
) -> dict[str, Any]:
    """Update a draft experiment's config."""
    try:
        result = executor.update_experiment(experiment_id, config)
        return {"experiment_id": result.experiment_id, "status": result.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{experiment_id}")
async def delete_experiment(experiment_id: str) -> dict[str, str]:
    """Delete an experiment and its result files."""
    try:
        executor.delete_experiment(experiment_id)
        return {"status": "deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@router.post("/{experiment_id}/validate")
async def validate_experiment(experiment_id: str) -> dict[str, Any]:
    """Validate experiment config and compute run count."""
    result = executor.validate_experiment(experiment_id)
    if not result["valid"]:
        raise HTTPException(status_code=400, detail={
            "errors": result["errors"],
            "warnings": result["warnings"],
        })
    return result


@router.post("/{experiment_id}/launch")
async def launch_experiment(experiment_id: str) -> dict[str, Any]:
    """Launch experiment execution."""
    try:
        return executor.launch_experiment(experiment_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{experiment_id}/pause")
async def pause_experiment(experiment_id: str) -> dict[str, str]:
    """Pause a running experiment."""
    try:
        executor.pause_experiment(experiment_id)
        return {"status": "paused"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
