"""Results query and visualization API routes."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from experiment_server.config import settings
from experiment_server.services import executor
from experiment_server.services.query import get_result_row, query_results
from experiment_server.services.reconstruct import reconstruct_strategy_config
from experiment_server.services.visualize import run_visualization

import pandas as pd

router = APIRouter(prefix="/experiments/{experiment_id}/results", tags=["results"])


@router.get("")
async def query_experiment_results(
    experiment_id: str,
    asset: str | None = None,
    timeframe: str | None = None,
    trigger_name: str | None = None,
    status: str | None = Query(None, alias="status"),
    min_trades: int = 0,
    min_sharpe: float | None = None,
    min_win_rate: float | None = None,
    reward_factor: float | None = None,
    cooldown_bars: int | None = None,
    atr_period: int | None = None,
    max_risk_per_trade: float | None = None,
    sort: str = "sharpe_ratio",
    order: str = "desc",
    limit: int = Query(50, le=500),
    offset: int = 0,
) -> dict[str, Any]:
    """Query experiment results with filters, sort, and pagination."""
    config = executor.get_experiment(experiment_id)
    if not config:
        raise HTTPException(status_code=404, detail="Experiment not found")

    exp_dir = os.path.join(settings.data_dir, "experiments", experiment_id)

    filters = {}
    if asset:
        filters["asset"] = asset
    if timeframe:
        filters["timeframe"] = timeframe
    if trigger_name:
        filters["trigger_name"] = trigger_name
    if status:
        filters["status"] = status
    if reward_factor is not None:
        filters["reward_factor"] = reward_factor
    if cooldown_bars is not None:
        filters["cooldown_bars"] = cooldown_bars
    if atr_period is not None:
        filters["atr_period"] = atr_period
    if max_risk_per_trade is not None:
        filters["max_risk_per_trade"] = max_risk_per_trade

    return query_results(
        experiment_dir=exp_dir,
        filters=filters,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
        min_trades=min_trades,
        min_sharpe=min_sharpe,
        min_win_rate=min_win_rate,
    )


@router.get("/{run_index}/ohlcv")
async def get_ohlcv(experiment_id: str, run_index: int) -> dict[str, Any]:
    """Return OHLCV candle data for a result's data file (no backtest needed)."""
    exp_dir = os.path.join(settings.data_dir, "experiments", experiment_id)
    row = get_result_row(exp_dir, run_index)
    if not row:
        raise HTTPException(status_code=404, detail="Result not found")

    data_file = row.get("data_file_path", "")
    csv_path = os.path.join(settings.ohlcv_dir, data_file)
    if not os.path.isfile(csv_path):
        raise HTTPException(status_code=404, detail=f"OHLCV file not found: {data_file}")

    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df.sort_values("timestamp", inplace=True)

    candles = []
    for _, r in df.iterrows():
        candles.append({
            "time": int(r["timestamp"].timestamp()),
            "open": round(float(r["open"]), 4),
            "high": round(float(r["high"]), 4),
            "low": round(float(r["low"]), 4),
            "close": round(float(r["close"]), 4),
            "volume": round(float(r["volume"]), 2),
        })

    return {"ohlcv": candles}


@router.get("/{run_index}/visualize")
async def visualize_result(
    experiment_id: str,
    run_index: int,
) -> dict[str, Any]:
    """Re-run a backtest and return full visualization data.

    Returns strategy config, metrics, provenance, OHLCV candles, and trade history.
    The backtest is re-executed from the stored config to regenerate trade data.
    """
    exp_dir = os.path.join(settings.data_dir, "experiments", experiment_id)
    row = get_result_row(exp_dir, run_index)

    if not row:
        raise HTTPException(status_code=404, detail="Result not found")

    strategy_config = reconstruct_strategy_config(row)

    # Re-run backtest in thread pool (CPU-bound, don't block event loop)
    viz = await asyncio.to_thread(run_visualization, row, strategy_config)

    # Use freshly computed metrics from the re-run (picks up any engine
    # fixes like Sortino/Calmar caps, corrected daily sampling, etc.).
    # Fall back to stored Parquet values only if re-run didn't produce metrics.
    fresh = viz.get("metrics", {})
    metrics = {
        "total_trades": fresh.get("total_trades", row.get("total_trades")),
        "win_rate": fresh.get("win_rate", row.get("win_rate")),
        "total_return": fresh.get("total_return", row.get("total_return")),
        "sharpe_ratio": fresh.get("sharpe_ratio", row.get("sharpe_ratio")),
        "sortino_ratio": fresh.get("sortino_ratio", row.get("sortino_ratio")),
        "max_drawdown": fresh.get("max_drawdown", row.get("max_drawdown")),
        "calmar_ratio": fresh.get("calmar_ratio", row.get("calmar_ratio")),
        "net_pnl": fresh.get("ending_balance", row.get("ending_balance", 0))
              - fresh.get("starting_balance", row.get("starting_balance", 0))
              if fresh else row.get("net_pnl"),
        "ending_balance": fresh.get("ending_balance", row.get("ending_balance")),
        "irr_annualized": fresh.get("irr_annualized"),
        "irr_daily": fresh.get("irr_daily"),
        "gain_to_pain_ratio": fresh.get("gain_to_pain_ratio"),
        "max_drawdown_duration": fresh.get("max_drawdown_duration"),
        "max_consecutive_wins": fresh.get("max_consecutive_wins"),
        "max_consecutive_losses": fresh.get("max_consecutive_losses"),
        "avg_daily_return": fresh.get("avg_daily_return"),
        "num_days": fresh.get("num_days"),
    }

    return {
        "run_index": run_index,
        "strategy_config": strategy_config,
        "metrics": metrics,
        "provenance": {
            "data_file_path": row.get("data_file_path"),
            "data_file_hash": row.get("data_file_hash"),
            "code_version": row.get("code_version"),
            "rng_seed": row.get("rng_seed"),
        },
        "trades": viz.get("trades", []),
        "ohlcv": viz.get("ohlcv", []),
        "viz_error": viz.get("error"),
    }
