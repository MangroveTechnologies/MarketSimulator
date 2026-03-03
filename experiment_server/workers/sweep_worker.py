"""Sweep worker -- RQ job function for backtest execution.

Each worker receives an assignment (experiment_id, dataset_key, worker_id,
list of run specs) and processes them sequentially:
1. Load OHLCV data once for the assigned dataset
2. Query completed run_indices from existing Parquet files (for resume)
3. For each run: set RNG seed, build strategy config, run backtest, buffer row
4. Flush Parquet chunks at chunk_size intervals
5. Publish progress to Redis Streams after each run

Workers are fully independent -- no shared state, no IPC.
"""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from typing import Any

import redis as redis_lib

from experiment_server.config import settings
from experiment_server.services.dataset import compute_file_hash
from experiment_server.services.plan_generator import RunSpec
from experiment_server.services.query import count_completed
from experiment_server.services.reconstruct import flatten_strategy_config
from experiment_server.workers.parquet_writer import ParquetChunkWriter

logger = logging.getLogger(__name__)


def _get_dataset_field(experiment_config: dict, data_file: str, field: str) -> Any:
    """Look up a dataset field from the experiment config."""
    for ds in experiment_config.get("datasets", []):
        if ds.get("file") == data_file:
            return ds.get(field, "" if field == "hash" else 0)
    return "" if field == "hash" else 0


def _suppress_engine_output():
    """Suppress noisy backtest engine loggers and stdout prints."""
    for name in [
        "MangroveAI.domains.backtesting",
        "MangroveAI.domains.strategies",
        "MangroveAI.domains.managers",
        "MangroveAI.domains.positions",
    ]:
        logging.getLogger(name).setLevel(logging.WARNING)


def _build_strategy_config(run: RunSpec) -> dict[str, Any]:
    """Build the complete strategy config from a RunSpec."""
    entry = json.loads(run.entry_json)
    exit_sigs = json.loads(run.exit_json)

    return {
        "name": f"exp_{run.dataset_key}_{run.trigger_name}_{run.run_index}",
        "asset": run.asset,
        "entry": entry,
        "exit": exit_sigs,
        "reward_factor": run.exec_config.get("reward_factor", 2.0),
        "execution_config": run.exec_config,
    }


def _extract_metrics(result: dict[str, Any]) -> dict[str, Any]:
    """Extract metric columns from a backtest result dict."""
    m = result.get("metrics", {})
    total_trades = int(m.get("total_trades") or 0)

    return {
        "total_trades": total_trades,
        "win_rate": round(float(m.get("win_rate") or 0), 4),
        "total_return": round(float(m.get("total_return") or 0), 4),
        "sharpe_ratio": round(float(m.get("sharpe_ratio") or 0), 4),
        "sortino_ratio": round(float(m.get("sortino_ratio") or 0), 4),
        "max_drawdown": round(float(m.get("max_drawdown") or 0), 4),
        "max_drawdown_duration": int(m.get("max_drawdown_duration") or 0),
        "calmar_ratio": round(float(m.get("calmar_ratio") or 0), 4),
        "gain_to_pain_ratio": round(float(m.get("gain_to_pain_ratio") or 0), 4),
        "irr_annualized": round(float(m.get("irr_annualized") or 0), 4),
        "irr_daily": round(float(m.get("irr_daily") or 0), 6),
        "avg_daily_return": round(float(m.get("avg_daily_return") or 0), 6),
        "max_consecutive_wins": int(m.get("max_consecutive_wins") or 0),
        "max_consecutive_losses": int(m.get("max_consecutive_losses") or 0),
        "num_days": int(m.get("num_days") or 0),
        "net_pnl": round(float(
            (m.get("ending_balance") or 10000) - (m.get("starting_balance") or 10000)
        ), 2),
        "starting_balance_result": float(m.get("starting_balance") or 10000),
        "ending_balance": float(m.get("ending_balance") or 10000),
        "status": "no_trades" if total_trades == 0 else "ok",
    }


def execute_sweep_job(
    experiment_id: str,
    experiment_dir: str,
    dataset_key: str,
    worker_id: int,
    runs: list[dict[str, Any]],
    experiment_config: dict[str, Any],
    experiment_seed: int = 42,
    code_version: str = "",
    chunk_size: int = 1024,
    redis_url: str | None = None,
    backtest_fn: Any = None,
) -> dict[str, Any]:
    """Execute a batch of backtest runs for one worker.

    This is the function that RQ calls. It can also be called directly
    for testing (with a mock backtest_fn).

    Args:
        experiment_id: Experiment identifier.
        experiment_dir: Path to the experiment directory.
        dataset_key: e.g., "BTC_1d".
        worker_id: Globally unique worker ID.
        runs: List of RunSpec dicts (serialized for RQ).
        experiment_config: Full experiment config dict (for Parquet metadata).
        experiment_seed: Seed for RNG seeding per run.
        code_version: Git SHA for provenance.
        chunk_size: Rows per Parquet chunk.
        redis_url: Redis connection URL (None to skip progress publishing).
        backtest_fn: Callable for running backtests. If None, imports from
            MangroveAI (requires /app/MangroveAI on sys.path).

    Returns:
        Summary dict with completed, errors, skipped counts.
    """
    # Deserialize RunSpec objects
    run_specs = [RunSpec(**r) if isinstance(r, dict) else r for r in runs]

    # Set up output directory
    output_dir = os.path.join(experiment_dir, "results", dataset_key)
    os.makedirs(output_dir, exist_ok=True)

    # Check completed runs for resume
    completed_indices = count_completed(experiment_dir)
    skipped = 0

    # Set up Parquet writer
    writer = ParquetChunkWriter(
        output_dir=output_dir,
        worker_id=worker_id,
        chunk_size=chunk_size,
        experiment_config=experiment_config,
    )

    # Set up Redis for progress publishing
    r = None
    stream_key = f"exp:{experiment_id}:progress"
    if redis_url:
        try:
            r = redis_lib.from_url(redis_url)
        except Exception as exc:
            logger.warning("Could not connect to Redis: %s", exc)

    # Load backtest function and OHLCV data
    _df_cache: dict[str, Any] = {}       # dataset_key -> primary DataFrame
    _daily_cache: dict[str, Any] = {}    # dataset_key -> daily companion DataFrame

    if backtest_fn is None:
        _suppress_engine_output()
        sys.path.insert(0, "/app")
        # Suppress stdout from the backtest engine (print-heavy)
        _devnull = open(os.devnull, "w")

        from MangroveAI.domains.backtesting.services import run_backtest
        from MangroveAI.domains.backtesting.domain_models.requests import BacktestRequest
        from MangroveAI.domains.backtesting import data_source as ds_module
        from MangroveAI.domains.positions.position import Position

        import pandas as pd

        from experiment_server.services.ohlcv_utils import (
            inject_ohlcv_for_run, load_ohlcv_csv,
            companion_daily_filename,
        )

        _use_mangrove = True
    else:
        _use_mangrove = False

    completed = 0
    errors = 0
    t_start = time.time()

    for run in run_specs:
        if run.run_index in completed_indices:
            skipped += 1
            continue

        # Deterministic RNG seed per run
        run_seed = experiment_seed * 1000000 + run.run_index
        random.seed(run_seed)

        strategy_config = _build_strategy_config(run)
        t0 = time.time()

        try:
            if _use_mangrove:
                # Load OHLCV data (once per dataset, cached)
                dk = run.dataset_key
                ohlcv_dir = os.environ.get(
                    "EXP_OHLCV_DIR", "/app/MarketSimulator/data/ohlcv",
                )
                if dk not in _df_cache:
                    _df_cache[dk] = load_ohlcv_csv(
                        os.path.join(ohlcv_dir, run.data_file)
                    )
                    # Pre-load daily companion (if sub-daily)
                    if run.timeframe.lower() != "1d":
                        companion = companion_daily_filename(run.data_file)
                        companion_path = os.path.join(ohlcv_dir, companion)
                        if os.path.isfile(companion_path):
                            _daily_cache[dk] = load_ohlcv_csv(companion_path)

                # Parse dates from the run spec
                start_dt = datetime.strptime(run.start_date, "%Y-%m-%d")
                end_dt = datetime.strptime(run.end_date, "%Y-%m-%d")

                ec = run.exec_config
                atr_period = int(ec.get("atr_period", 14))

                # Inject both signal TF and daily into _OHLCV_CACHE
                inject_ohlcv_for_run(
                    ds_module=ds_module,
                    ohlcv_dir=ohlcv_dir,
                    data_file=run.data_file,
                    asset=run.asset,
                    timeframe=run.timeframe,
                    start_date=start_dt,
                    end_date=end_dt,
                    atr_period=atr_period,
                    df_primary=_df_cache[dk],
                    df_daily=_daily_cache.get(dk),
                )

                # Build BacktestRequest
                request = BacktestRequest(
                    initial_balance=float(ec.get("initial_balance", 10000)),
                    min_balance_threshold=float(ec.get("min_balance_threshold", 0.1)),
                    min_trade_amount=float(ec.get("min_trade_amount", 25)),
                    max_open_positions=int(ec.get("max_open_positions", 10)),
                    max_trades_per_day=int(ec.get("max_trades_per_day", 50)),
                    max_risk_per_trade=float(ec.get("max_risk_per_trade", 0.01)),
                    max_units_per_trade=float(ec.get("max_units_per_trade", 10000)),
                    max_trade_amount=float(ec.get("max_trade_amount", 10000000)),
                    volatility_window=int(ec.get("volatility_window", 24)),
                    target_volatility=float(ec.get("target_volatility", 0.02)),
                    volatility_mode=str(ec.get("volatility_mode", "stddev")),
                    enable_volatility_adjustment=bool(ec.get("enable_volatility_adjustment", False)),
                    cooldown_bars=int(ec.get("cooldown_bars", 24)),
                    daily_momentum_limit=float(ec.get("daily_momentum_limit", 3)),
                    weekly_momentum_limit=float(ec.get("weekly_momentum_limit", 3)),
                    asset=f"{run.asset.upper()}-USDT",
                    interval=run.timeframe,
                    start_date=start_dt,
                    end_date=end_dt,
                    strategy_json=json.dumps(strategy_config),
                    execution_config=ec,
                )

                # Suppress stdout during backtest
                old_stdout = sys.stdout
                sys.stdout = _devnull
                try:
                    result = run_backtest(request)
                finally:
                    sys.stdout = old_stdout

                # Clear position state (engine singleton)
                Position.positions.clear()
            else:
                result = backtest_fn(strategy_config, run)

            if not result.get("success"):
                raise RuntimeError(result.get("error", "unknown error"))

            metrics = _extract_metrics(result)
            completed += 1

        except Exception as e:
            metrics = {
                "total_trades": 0, "win_rate": 0, "total_return": 0,
                "sharpe_ratio": 0, "sortino_ratio": 0, "max_drawdown": 0,
                "max_drawdown_duration": 0, "calmar_ratio": 0,
                "gain_to_pain_ratio": 0, "irr_annualized": 0, "irr_daily": 0,
                "avg_daily_return": 0, "max_consecutive_wins": 0,
                "max_consecutive_losses": 0, "num_days": 0, "net_pnl": 0,
                "starting_balance_result": 10000, "ending_balance": 10000,
                "status": "error",
            }
            metrics["error_msg"] = str(e)[:200]
            errors += 1

        elapsed = round(time.time() - t0, 2)

        # Compute config hash for dedup
        from experiment_server.services.hashing import compute_config_hash
        cfg_hash = compute_config_hash(
            run.entry_json, run.exit_json, run.exec_config,
            run.asset, run.timeframe, run.start_date, run.end_date,
        )

        # Build the full result row
        row = flatten_strategy_config(
            strategy_config,
            run_index=run.run_index,
            experiment_id=experiment_id,
            config_hash=cfg_hash,
            code_version=code_version,
            rng_seed=run_seed,
            data_file_path=run.data_file,
            data_file_hash=_get_dataset_field(experiment_config, run.data_file, "hash"),
            data_file_rows=_get_dataset_field(experiment_config, run.data_file, "rows"),
            timeframe=run.timeframe,
            start_date=run.start_date,
            end_date=run.end_date,
            elapsed_seconds=elapsed,
            completed_at=datetime.now(timezone.utc).isoformat(),
            **metrics,
        )

        writer.add_row(row)

        # Publish progress
        if r:
            try:
                r.xadd(stream_key, {
                    "worker_id": str(worker_id),
                    "dataset": dataset_key,
                    "completed": str(completed),
                    "errors": str(errors),
                    "skipped": str(skipped),
                    "run_index": str(run.run_index),
                })
            except Exception:
                pass  # Non-critical

    writer.close()
    total_elapsed = round(time.time() - t_start, 2)

    # Publish completion
    if r:
        try:
            r.xadd(stream_key, {
                "worker_id": str(worker_id),
                "dataset": dataset_key,
                "status": "done",
                "completed": str(completed),
                "errors": str(errors),
                "skipped": str(skipped),
                "elapsed": str(total_elapsed),
            })
        except Exception:
            pass

    return {
        "worker_id": worker_id,
        "dataset": dataset_key,
        "completed": completed,
        "errors": errors,
        "skipped": skipped,
        "elapsed_seconds": total_elapsed,
    }
