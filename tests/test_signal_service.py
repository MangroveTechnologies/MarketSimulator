"""Tests for signal metadata service."""

import json
import os
import tempfile

from experiment_server.services.signal import load_signals


def _write_test_metadata(path: str) -> None:
    metadata = {
        "ema_cross_up": {
            "type": "TRIGGER",
            "description": "EMA crossover up",
            "requires": ["Close"],
            "params": {
                "window_fast": {"type": "int", "min": 5, "max": 30, "default": 9},
                "window_slow": {"type": "int", "min": 20, "max": 100, "default": 21},
            },
        },
        "rsi_oversold": {
            "type": "FILTER",
            "description": "RSI below threshold",
            "requires": ["Close"],
            "params": {
                "window": {"type": "int", "min": 7, "max": 28, "default": 14},
                "threshold": {"type": "float", "min": 20, "max": 40, "default": 30},
            },
            "constraints": [],
        },
        "macd_bullish_cross": {
            "type": "TRIGGER",
            "description": "MACD bullish crossover",
            "requires": ["Close"],
            "params": {
                "window_fast": {"type": "int", "min": 8, "max": 20, "default": 12},
                "window_slow": {"type": "int", "min": 20, "max": 35, "default": 26},
                "window_sign": {"type": "int", "min": 5, "max": 15, "default": 9},
            },
            "constraints": [["window_fast", "<", "window_slow"]],
        },
    }
    with open(path, "w") as f:
        json.dump(metadata, f)


def test_load_all_signals():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    signals = load_signals(path)
    assert len(signals) == 3
    names = [s["name"] for s in signals]
    assert "ema_cross_up" in names
    assert "rsi_oversold" in names
    assert "macd_bullish_cross" in names
    os.unlink(path)


def test_filter_by_type():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    triggers = load_signals(path, signal_type="TRIGGER")
    assert len(triggers) == 2
    assert all(s["type"] == "TRIGGER" for s in triggers)

    filters = load_signals(path, signal_type="FILTER")
    assert len(filters) == 1
    assert filters[0]["name"] == "rsi_oversold"
    os.unlink(path)


def test_search_by_name():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    results = load_signals(path, search="rsi")
    assert len(results) == 1
    assert results[0]["name"] == "rsi_oversold"

    results = load_signals(path, search="cross")
    assert len(results) == 2
    os.unlink(path)


def test_param_metadata_structure():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    signals = load_signals(path)
    ema = next(s for s in signals if s["name"] == "ema_cross_up")

    assert "window_fast" in ema["params"]
    wf = ema["params"]["window_fast"]
    assert wf["type"] == "int"
    assert wf["min"] == 5
    assert wf["max"] == 30
    assert wf["default"] == 9
    os.unlink(path)


def test_explicit_constraints_preserved():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    signals = load_signals(path)
    macd = next(s for s in signals if s["name"] == "macd_bullish_cross")
    assert macd["constraints"] == [["window_fast", "<", "window_slow"]]
    os.unlink(path)


def test_inferred_constraints_for_fast_slow():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    signals = load_signals(path)
    ema = next(s for s in signals if s["name"] == "ema_cross_up")
    # No explicit constraints in metadata, but should infer fast < slow
    assert ema["constraints"] == [["window_fast", "<", "window_slow"]]
    os.unlink(path)


def test_results_sorted_by_name():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = f.name
    _write_test_metadata(path)

    signals = load_signals(path)
    names = [s["name"] for s in signals]
    assert names == sorted(names)
    os.unlink(path)
