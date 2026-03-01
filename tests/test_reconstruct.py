"""Tests for strategy config reconstruction and flattening."""

import json

from experiment_server.services.reconstruct import (
    flatten_strategy_config,
    reconstruct_strategy_config,
)


def _make_strategy_config() -> dict:
    return {
        "name": "test_strat",
        "asset": "BTC",
        "entry": [
            {"name": "ema_cross_up", "signal_type": "TRIGGER",
             "timeframe": "1d", "params": {"window_fast": 9, "window_slow": 21}},
            {"name": "rsi_oversold", "signal_type": "FILTER",
             "timeframe": "1d", "params": {"window": 14, "threshold": 30}},
        ],
        "exit": [
            {"name": "rsi_cross_up", "signal_type": "TRIGGER",
             "timeframe": "1d", "params": {"threshold": 70}},
        ],
        "reward_factor": 3.0,
        "execution_config": {
            "max_risk_per_trade": 0.02,
            "stop_loss_calculation": "dynamic_atr",
            "atr_period": 21,
            "atr_volatility_factor": 1.5,
            "atr_short_weight": 0.7,
            "atr_long_weight": 0.3,
            "initial_balance": 10000,
            "min_balance_threshold": 0.1,
            "min_trade_amount": 25,
            "max_open_positions": 3,
            "max_trades_per_day": 10,
            "max_units_per_trade": 10000,
            "max_trade_amount": 10000000,
            "volatility_window": 20,
            "target_volatility": 0.01,
            "volatility_mode": "stddev",
            "enable_volatility_adjustment": True,
            "max_hold_time_hours": None,
            "cooldown_bars": 1,
            "daily_momentum_limit": 3,
            "weekly_momentum_limit": 3,
            "max_hold_bars": 200,
            "exit_on_loss_after_bars": 100,
            "exit_on_profit_after_bars": 200,
            "profit_threshold_pct": 0.08,
            "slippage_pct": 0.005,
            "fee_pct": 0.005,
        },
    }


def test_round_trip():
    """Flatten a config and reconstruct it -- should match the original."""
    original = _make_strategy_config()
    flat = flatten_strategy_config(original, run_index=42, experiment_id="exp_test")
    reconstructed = reconstruct_strategy_config(flat)

    assert reconstructed["name"] == original["name"]
    assert reconstructed["asset"] == original["asset"]
    assert reconstructed["reward_factor"] == original["reward_factor"]
    assert reconstructed["entry"] == original["entry"]
    assert reconstructed["exit"] == original["exit"]

    for key in original["execution_config"]:
        assert reconstructed["execution_config"][key] == original["execution_config"][key], \
            f"Mismatch on exec config key '{key}'"


def test_flatten_trigger_name_extracted():
    config = _make_strategy_config()
    flat = flatten_strategy_config(config)
    assert flat["trigger_name"] == "ema_cross_up"


def test_flatten_signal_counts():
    config = _make_strategy_config()
    flat = flatten_strategy_config(config)
    assert flat["num_entry_signals"] == 2
    assert flat["num_exit_signals"] == 1


def test_flatten_entry_json_valid():
    config = _make_strategy_config()
    flat = flatten_strategy_config(config)
    entry = json.loads(flat["entry_json"])
    assert len(entry) == 2
    assert entry[0]["name"] == "ema_cross_up"
    assert entry[0]["params"]["window_fast"] == 9


def test_flatten_exit_json_valid():
    config = _make_strategy_config()
    flat = flatten_strategy_config(config)
    exit_sigs = json.loads(flat["exit_json"])
    assert len(exit_sigs) == 1
    assert exit_sigs[0]["name"] == "rsi_cross_up"


def test_flatten_extra_fields_merged():
    config = _make_strategy_config()
    flat = flatten_strategy_config(
        config,
        run_index=7,
        experiment_id="exp_123",
        sharpe_ratio=4.5,
        status="ok",
        data_file_hash="sha256:abc",
    )
    assert flat["run_index"] == 7
    assert flat["experiment_id"] == "exp_123"
    assert flat["sharpe_ratio"] == 4.5
    assert flat["status"] == "ok"
    assert flat["data_file_hash"] == "sha256:abc"


def test_empty_exit_signals():
    config = _make_strategy_config()
    config["exit"] = []
    flat = flatten_strategy_config(config)
    reconstructed = reconstruct_strategy_config(flat)
    assert reconstructed["exit"] == []
    assert flat["num_exit_signals"] == 0


def test_enable_volatility_adjustment_remapped():
    """The Parquet column is 'enable_volatility_adj' but the config key
    is 'enable_volatility_adjustment'. Verify the remap works."""
    config = _make_strategy_config()
    config["execution_config"]["enable_volatility_adjustment"] = True
    flat = flatten_strategy_config(config)
    assert flat["enable_volatility_adj"] is True

    reconstructed = reconstruct_strategy_config(flat)
    assert reconstructed["execution_config"]["enable_volatility_adjustment"] is True
