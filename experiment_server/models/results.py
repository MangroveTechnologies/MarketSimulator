"""Pydantic models for experiment results and progress events."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ResultRow(BaseModel):
    """A single backtest result for API responses.

    This is a subset of the full Parquet schema -- only the fields needed
    for the results table in the Explore view. The full row can be fetched
    separately for visualization.
    """

    run_index: int
    experiment_id: str
    asset: str
    timeframe: str
    trigger_name: str
    num_entry_signals: int
    num_exit_signals: int = 0
    reward_factor: float
    max_risk_per_trade: float
    cooldown_bars: int
    atr_period: int
    atr_volatility_factor: float
    total_trades: int
    win_rate: float
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    gain_to_pain_ratio: float = 0.0
    net_pnl: float
    ending_balance: float
    status: str
    error_msg: str | None = None
    elapsed_seconds: float = 0.0


class DatasetProgress(BaseModel):
    """Progress for a single dataset within a running experiment."""

    completed: int
    total: int
    status: Literal["pending", "running", "done", "failed"]


class ProgressEvent(BaseModel):
    """Real-time progress update sent via SSE."""

    completed: int
    total: int
    rate: float
    eta_seconds: float
    elapsed_seconds: float
    errors: int
    no_trades: int
    per_dataset: dict[str, DatasetProgress]
