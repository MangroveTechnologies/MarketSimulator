"""Strategy config reconstruction from Parquet result rows.

Rebuilds the complete strategy config object from the flat columns + JSON
fields stored in a result row. This is the inverse of the flattening done
by the sweep worker when writing results.

The reconstructed config is identical to the original that was passed to
run_single_backtest(), enabling exact reproduction of any result.
"""

from __future__ import annotations

import json
from typing import Any

# Execution config field names in the order they appear in the Parquet schema.
# These are the flat columns that get reassembled into the execution_config dict.
EXEC_CONFIG_FIELDS = [
    "max_risk_per_trade",
    "stop_loss_calculation",
    "atr_period",
    "atr_volatility_factor",
    "atr_short_weight",
    "atr_long_weight",
    "initial_balance",
    "min_balance_threshold",
    "min_trade_amount",
    "max_open_positions",
    "max_trades_per_day",
    "max_units_per_trade",
    "max_trade_amount",
    "volatility_window",
    "target_volatility",
    "volatility_mode",
    "enable_volatility_adj",
    "max_hold_time_hours",
    "cooldown_bars",
    "daily_momentum_limit",
    "weekly_momentum_limit",
    "max_hold_bars",
    "exit_on_loss_after_bars",
    "exit_on_profit_after_bars",
    "profit_threshold_pct",
    "slippage_pct",
    "fee_pct",
]

# Map from Parquet column name to strategy config key where they differ
_FIELD_REMAP = {
    "enable_volatility_adj": "enable_volatility_adjustment",
}


def reconstruct_strategy_config(row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a complete strategy config from a Parquet result row.

    Args:
        row: A dict from a Parquet result row (e.g., from get_result_row()).

    Returns:
        A complete strategy config dict matching the format expected by
        MangroveAI's run_single_backtest().
    """
    exec_config = {}
    for field in EXEC_CONFIG_FIELDS:
        config_key = _FIELD_REMAP.get(field, field)
        value = row.get(field)
        # Convert numpy/pandas types to native Python
        if hasattr(value, "item"):
            value = value.item()
        exec_config[config_key] = value

    entry = json.loads(row.get("entry_json", "[]"))
    exit_sigs = json.loads(row.get("exit_json", "[]"))

    reward_factor = row.get("reward_factor")
    if hasattr(reward_factor, "item"):
        reward_factor = reward_factor.item()

    return {
        "name": row.get("strategy_name", ""),
        "asset": row.get("asset", ""),
        "entry": entry,
        "exit": exit_sigs,
        "reward_factor": reward_factor,
        "execution_config": exec_config,
    }


def flatten_strategy_config(
    config: dict[str, Any],
    run_index: int = 0,
    experiment_id: str = "",
    **extra_fields: Any,
) -> dict[str, Any]:
    """Flatten a strategy config into a Parquet-ready row dict.

    This is the inverse of reconstruct_strategy_config(). Used by the
    sweep worker to build result rows.

    Args:
        config: Complete strategy config dict.
        run_index: The run_index for this result.
        experiment_id: The experiment ID.
        **extra_fields: Additional fields (metrics, provenance, metadata).

    Returns:
        A flat dict with all 67 columns matching the Parquet schema.
    """
    entry = config.get("entry", [])
    exit_sigs = config.get("exit", [])
    exec_config = config.get("execution_config", {})

    # Find the trigger name from entry signals
    trigger_name = ""
    for sig in entry:
        if sig.get("signal_type") == "TRIGGER":
            trigger_name = sig.get("name", "")
            break

    row = {
        "experiment_id": experiment_id,
        "run_index": run_index,
        "strategy_name": config.get("name", ""),
        "asset": config.get("asset", ""),
        "entry_json": json.dumps(entry),
        "exit_json": json.dumps(exit_sigs),
        "trigger_name": trigger_name,
        "num_entry_signals": len(entry),
        "num_exit_signals": len(exit_sigs),
        "reward_factor": config.get("reward_factor", 2.0),
    }

    # Flatten exec config fields
    for field in EXEC_CONFIG_FIELDS:
        config_key = _FIELD_REMAP.get(field, field)
        row[field] = exec_config.get(config_key)

    # Merge extra fields (provenance, metrics, metadata)
    row.update(extra_fields)

    return row
