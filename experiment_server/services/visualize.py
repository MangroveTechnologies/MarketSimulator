"""Backtest re-execution for result visualization.

Re-runs a single backtest from stored Parquet data to produce:
- Full trade history with entry/exit timestamps and prices
- OHLCV candle data for charting

Injects local CSV data (signal TF + daily companion) into the engine's
_OHLCV_CACHE so it reads from files instead of calling CoinAPI. Uses the
same injection mechanism as the sweep worker.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any

import pandas as pd

from experiment_server.config import settings

logger = logging.getLogger(__name__)

# Lazy-loaded MangroveAI imports (only available inside Docker container)
_engine_available = False
_run_backtest = None
_BacktestRequest = None
_ds_module = None
_Position = None


def _ensure_engine():
    """Lazy-load the MangroveAI backtest engine.

    MangroveAI's __init__.py triggers app_config which resolves GCP secrets.
    We override ENVIRONMENT=sweep to use a secrets-free config file
    (sweep-config.json) since the backtest engine needs no external services.
    """
    global _engine_available, _run_backtest, _BacktestRequest, _ds_module, _Position
    if _run_backtest is not None:
        return

    old_env = os.environ.get("ENVIRONMENT")
    try:
        os.environ["ENVIRONMENT"] = "sweep"
        sys.path.insert(0, "/app")

        from MangroveAI.domains.backtesting.services import run_backtest
        from MangroveAI.domains.backtesting.domain_models.requests import BacktestRequest
        from MangroveAI.domains.backtesting import data_source as ds_module
        from MangroveAI.domains.positions.position import Position

        _run_backtest = run_backtest
        _BacktestRequest = BacktestRequest
        _ds_module = ds_module
        _Position = Position
        _engine_available = True

        for name in [
            "MangroveAI.domains.backtesting",
            "MangroveAI.domains.strategies",
            "MangroveAI.domains.managers",
            "MangroveAI.domains.positions",
        ]:
            logging.getLogger(name).setLevel(logging.WARNING)

    except:  # noqa: E722 -- MangroveAI init can raise SystemExit
        _engine_available = False
        logger.warning("MangroveAI not available -- visualize will return empty trades")
    finally:
        if old_env is not None:
            os.environ["ENVIRONMENT"] = old_env


def run_visualization(row: dict[str, Any], strategy_config: dict[str, Any]) -> dict[str, Any]:
    """Re-run a backtest and return trades + OHLCV data."""
    _ensure_engine()

    if not _engine_available:
        return {"trades": [], "ohlcv": [], "error": "MangroveAI engine not available"}

    from experiment_server.services.ohlcv_utils import (
        inject_ohlcv_for_run, cleanup_ohlcv_cache, load_ohlcv_csv,
    )

    asset = row.get("asset", "")
    timeframe = row.get("timeframe", "")
    data_file = row.get("data_file_path", "")
    start_date_str = row.get("start_date", "")
    end_date_str = row.get("end_date", "")

    csv_path = os.path.join(settings.ohlcv_dir, data_file)
    if not os.path.isfile(csv_path):
        return {"trades": [], "ohlcv": [], "error": f"OHLCV file not found: {csv_path}"}

    df = load_ohlcv_csv(csv_path)

    start_dt = datetime.strptime(start_date_str, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date_str, "%Y-%m-%d")

    ec = strategy_config.get("execution_config", {})
    atr_period = int(ec.get("atr_period", 14) or 14)

    def _v(key, default):
        """Get value from ec, coalescing None to default."""
        val = ec.get(key)
        return default if val is None else val

    # Inject signal TF + daily companion into _OHLCV_CACHE
    injected_keys = inject_ohlcv_for_run(
        ds_module=_ds_module,
        ohlcv_dir=settings.ohlcv_dir,
        data_file=data_file,
        asset=asset,
        timeframe=timeframe,
        start_date=start_dt,
        end_date=end_dt,
        atr_period=atr_period,
        df_primary=df,
    )

    request = _BacktestRequest(
        initial_balance=float(_v("initial_balance", 10000)),
        min_balance_threshold=float(_v("min_balance_threshold", 0.1)),
        min_trade_amount=float(_v("min_trade_amount", 25)),
        max_open_positions=int(_v("max_open_positions", 10)),
        max_trades_per_day=int(_v("max_trades_per_day", 50)),
        max_risk_per_trade=float(_v("max_risk_per_trade", 0.01)),
        max_units_per_trade=float(_v("max_units_per_trade", 10000)),
        max_trade_amount=float(_v("max_trade_amount", 10000000)),
        volatility_window=int(_v("volatility_window", 24)),
        target_volatility=float(_v("target_volatility", 0.02)),
        volatility_mode=str(_v("volatility_mode", "stddev")),
        enable_volatility_adjustment=bool(_v("enable_volatility_adjustment", False)),
        cooldown_bars=int(_v("cooldown_bars", 24)),
        daily_momentum_limit=float(_v("daily_momentum_limit", 3)),
        weekly_momentum_limit=float(_v("weekly_momentum_limit", 3)),
        asset=f"{asset.upper()}-USDT",
        interval=timeframe,
        start_date=start_dt,
        end_date=end_dt,
        strategy_json=json.dumps(strategy_config),
        execution_config=ec,
    )

    # Run backtest with stdout suppressed
    devnull = open(os.devnull, "w")
    old_stdout = sys.stdout
    sys.stdout = devnull
    try:
        result = _run_backtest(request)
    finally:
        sys.stdout = old_stdout
        devnull.close()
        cleanup_ohlcv_cache(_ds_module, injected_keys)

    _Position.positions.clear()

    if not result.get("success"):
        return {
            "trades": [],
            "ohlcv": _format_ohlcv(df),
            "error": result.get("error", "Backtest failed"),
        }

    trades = []
    for t in result.get("trades", []):
        trades.append({
            "trade_id": t.trade_id,
            "outcome": t.outcome,
            "profit_loss": round(t.profit_loss, 2),
            "side": t.side,
            "entry_price": round(t.entry_price, 4),
            "exit_price": round(t.exit_price, 4),
            "position_size": round(t.position_size, 6),
            "beginning_balance": round(t.beginning_balance, 2),
            "ending_balance": round(t.ending_balance, 2),
            "entry_timestamp": t.entry_timestamp.isoformat() if t.entry_timestamp else None,
            "exit_timestamp": t.exit_timestamp.isoformat() if t.exit_timestamp else None,
            "exit_reason": getattr(t, "exit_reason", None),
            "stop_loss_price": round(t.stop_loss_price, 4) if t.stop_loss_price else None,
            "take_profit_price": round(t.take_profit_price, 4) if t.take_profit_price else None,
        })

    return {
        "trades": trades,
        "ohlcv": _format_ohlcv(df),
        "metrics": result.get("metrics", {}),
    }


def _format_ohlcv(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Format OHLCV dataframe for lightweight-charts (Unix timestamp seconds)."""
    records = []
    for _, row in df.iterrows():
        records.append({
            "time": int(row["timestamp"].timestamp()),
            "open": round(float(row["open"]), 4),
            "high": round(float(row["high"]), 4),
            "low": round(float(row["low"]), 4),
            "close": round(float(row["close"]), 4),
            "volume": round(float(row["volume"]), 2),
        })
    return records
