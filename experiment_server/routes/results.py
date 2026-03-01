"""Results query and visualization API routes."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from experiment_server.config import settings
from experiment_server.services import executor
from experiment_server.services.query import get_result_row, query_results
from experiment_server.services.reconstruct import reconstruct_strategy_config

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


@router.get("/{run_index}/visualize")
async def visualize_result(
    experiment_id: str,
    run_index: int,
) -> dict[str, Any]:
    """Fetch a single result row and reconstruct its strategy config.

    In the full implementation, this re-runs the backtest and caches trades
    in Redis. For now, it returns the reconstructed config and stored metrics.
    """
    exp_dir = os.path.join(settings.data_dir, "experiments", experiment_id)
    row = get_result_row(exp_dir, run_index)

    if not row:
        raise HTTPException(status_code=404, detail="Result not found")

    strategy_config = reconstruct_strategy_config(row)

    return {
        "run_index": run_index,
        "strategy_config": strategy_config,
        "metrics": {
            "total_trades": row.get("total_trades"),
            "win_rate": row.get("win_rate"),
            "total_return": row.get("total_return"),
            "sharpe_ratio": row.get("sharpe_ratio"),
            "sortino_ratio": row.get("sortino_ratio"),
            "max_drawdown": row.get("max_drawdown"),
            "calmar_ratio": row.get("calmar_ratio"),
            "net_pnl": row.get("net_pnl"),
            "ending_balance": row.get("ending_balance"),
        },
        "provenance": {
            "data_file_path": row.get("data_file_path"),
            "data_file_hash": row.get("data_file_hash"),
            "code_version": row.get("code_version"),
            "rng_seed": row.get("rng_seed"),
        },
        "trades": [],  # populated by re-running backtest (future: Redis cache)
    }
