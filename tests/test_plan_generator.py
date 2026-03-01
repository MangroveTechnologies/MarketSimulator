"""Tests for the deterministic plan generator."""

import json

from experiment_server.models.experiment import (
    DatasetSelection,
    ExecConfigSweep,
    ExperimentConfig,
    ParamSweep,
    SignalConfig,
    SignalSelection,
)
from experiment_server.services.plan_generator import (
    apply_constraints,
    compute_total_runs,
    expand_param_sweep,
    generate_exec_config_variants,
    generate_plan,
    generate_signal_param_combos,
)


# ---------------------------------------------------------------------------
# Helper: build minimal configs for tests
# ---------------------------------------------------------------------------

def _make_dataset() -> DatasetSelection:
    return DatasetSelection(
        asset="BTC", timeframe="1d", file="btc.csv",
        start_date="2022-08-01", end_date="2026-02-15",
    )


def _make_trigger(values_fast=None, values_slow=None) -> SignalConfig:
    return SignalConfig(
        name="ema_cross_up",
        signal_type="TRIGGER",
        timeframe="1d",
        params_sweep={
            "window_fast": ParamSweep(values=values_fast or [9, 15]),
            "window_slow": ParamSweep(values=values_slow or [21, 50]),
        },
    )


def _make_filter() -> SignalConfig:
    return SignalConfig(
        name="rsi_oversold",
        signal_type="FILTER",
        timeframe="1d",
        params_sweep={
            "window": ParamSweep(values=[14]),
            "threshold": ParamSweep(values=[25, 30]),
        },
    )


def _make_config(**overrides) -> ExperimentConfig:
    defaults = dict(
        name="test",
        seed=42,
        search_mode="grid",
        datasets=[_make_dataset()],
        entry_signals=SignalSelection(
            triggers=[_make_trigger()],
            filters=[_make_filter()],
        ),
        execution_config=ExecConfigSweep(base={"reward_factor": 2.0}),
    )
    defaults.update(overrides)
    return ExperimentConfig(**defaults)


# ---------------------------------------------------------------------------
# expand_param_sweep
# ---------------------------------------------------------------------------

def test_expand_explicit_values():
    sweep = ParamSweep(values=[1.5, 2.0, 3.0])
    assert expand_param_sweep(sweep) == [1.5, 2.0, 3.0]


def test_expand_range_int():
    sweep = ParamSweep(min=0, max=6, step=2)
    assert expand_param_sweep(sweep) == [0, 2, 4, 6]


def test_expand_range_float():
    sweep = ParamSweep(min=0.0, max=0.1, step=0.05)
    result = expand_param_sweep(sweep)
    assert len(result) == 3
    assert abs(result[0] - 0.0) < 1e-6
    assert abs(result[1] - 0.05) < 1e-6
    assert abs(result[2] - 0.1) < 1e-6


def test_expand_bool_values():
    sweep = ParamSweep(values=[True, False])
    assert expand_param_sweep(sweep) == [True, False]


# ---------------------------------------------------------------------------
# generate_signal_param_combos
# ---------------------------------------------------------------------------

def test_signal_param_combos_cartesian():
    sig = _make_trigger(values_fast=[5, 10], values_slow=[20, 40])
    combos = generate_signal_param_combos(sig)
    assert len(combos) == 4  # 2 x 2
    assert {"window_fast": 5, "window_slow": 20} in combos
    assert {"window_fast": 10, "window_slow": 40} in combos


def test_signal_no_params():
    sig = SignalConfig(name="test", signal_type="TRIGGER", params_sweep={})
    combos = generate_signal_param_combos(sig)
    assert combos == [{}]


# ---------------------------------------------------------------------------
# apply_constraints
# ---------------------------------------------------------------------------

def test_constraints_filter_invalid():
    combos = [
        {"window_fast": 5, "window_slow": 20},
        {"window_fast": 25, "window_slow": 20},  # invalid: fast >= slow
        {"window_fast": 10, "window_slow": 10},  # invalid: fast == slow
    ]
    valid = apply_constraints(combos, [["window_fast", "<", "window_slow"]])
    assert len(valid) == 1
    assert valid[0]["window_fast"] == 5


def test_constraints_allow_overlapping_ranges():
    # window_fast [1..50], window_slow [25..100], constraint fast < slow
    combos = [
        {"window_fast": 25, "window_slow": 26},  # valid
        {"window_fast": 30, "window_slow": 50},  # valid
        {"window_fast": 50, "window_slow": 25},  # invalid
        {"window_fast": 49, "window_slow": 50},  # valid
    ]
    valid = apply_constraints(combos, [["window_fast", "<", "window_slow"]])
    assert len(valid) == 3


def test_no_constraints_passes_all():
    combos = [{"a": 1}, {"a": 2}]
    assert apply_constraints(combos, []) == combos


# ---------------------------------------------------------------------------
# generate_exec_config_variants
# ---------------------------------------------------------------------------

def test_exec_no_sweep():
    ec = ExecConfigSweep(base={"reward_factor": 2.0, "cooldown_bars": 3})
    variants = generate_exec_config_variants(ec)
    assert len(variants) == 1
    assert variants[0]["reward_factor"] == 2.0


def test_exec_sweep_cross_product():
    ec = ExecConfigSweep(
        base={"reward_factor": 2.0, "cooldown_bars": 3},
        sweep_axes=[
            {"param": "reward_factor", "values": [1.5, 2.0, 3.0]},
            {"param": "cooldown_bars", "values": [0, 3]},
        ],
    )
    variants = generate_exec_config_variants(ec)
    assert len(variants) == 6  # 3 x 2
    rfs = {v["reward_factor"] for v in variants}
    assert rfs == {1.5, 2.0, 3.0}


def test_exec_sweep_with_range():
    ec = ExecConfigSweep(
        base={"atr_period": 14},
        sweep_axes=[
            {"param": "atr_period", "min": 7, "max": 21, "step": 7},
        ],
    )
    variants = generate_exec_config_variants(ec)
    assert len(variants) == 3
    periods = [v["atr_period"] for v in variants]
    assert periods == [7, 14, 21]


# ---------------------------------------------------------------------------
# generate_plan (full integration)
# ---------------------------------------------------------------------------

def test_grid_search_total_count():
    config = _make_config()
    plan = generate_plan(config)
    # 1 dataset x 1 trigger x (2 fast x 2 slow) x 1 filter x (1 window x 2 threshold) x 1 exec = 8
    assert len(plan) == 8


def test_grid_search_unique_run_indices():
    config = _make_config()
    plan = generate_plan(config)
    indices = [r.run_index for r in plan]
    assert len(set(indices)) == len(indices)
    assert set(indices) == set(range(len(plan)))


def test_random_search_respects_n():
    config = _make_config(search_mode="random", n_random=3)
    plan = generate_plan(config)
    assert len(plan) == 3


def test_same_seed_same_plan():
    config = _make_config(search_mode="random", n_random=5)
    plan1 = generate_plan(config)
    plan2 = generate_plan(config)
    indices1 = [r.run_index for r in plan1]
    indices2 = [r.run_index for r in plan2]
    assert indices1 == indices2
    triggers1 = [r.trigger_name for r in plan1]
    triggers2 = [r.trigger_name for r in plan2]
    assert triggers1 == triggers2


def test_different_seed_different_plan():
    config1 = _make_config(search_mode="random", n_random=5, seed=1)
    config2 = _make_config(search_mode="random", n_random=5, seed=2)
    plan1 = generate_plan(config1)
    plan2 = generate_plan(config2)
    # Very unlikely to be identical with different seeds
    triggers1 = [r.trigger_name for r in plan1]
    triggers2 = [r.trigger_name for r in plan2]
    entries1 = [r.entry_json for r in plan1]
    entries2 = [r.entry_json for r in plan2]
    # At least the order should differ (shuffled with different seeds)
    assert entries1 != entries2 or triggers1 != triggers2


def test_entry_json_contains_valid_signals():
    config = _make_config()
    plan = generate_plan(config)
    for run in plan:
        entry = json.loads(run.entry_json)
        assert len(entry) >= 2  # at least 1 trigger + 1 filter
        trigger = entry[0]
        assert trigger["signal_type"] == "TRIGGER"
        assert trigger["name"] == "ema_cross_up"
        assert "window_fast" in trigger["params"]
        assert "window_slow" in trigger["params"]


def test_exec_config_in_runspec():
    config = _make_config(
        execution_config=ExecConfigSweep(
            base={"reward_factor": 2.0, "cooldown_bars": 3},
            sweep_axes=[{"param": "reward_factor", "values": [1.5, 3.0]}],
        ),
    )
    plan = generate_plan(config)
    rfs = {run.exec_config["reward_factor"] for run in plan}
    assert 1.5 in rfs
    assert 3.0 in rfs


def test_multiple_datasets():
    config = _make_config(
        datasets=[
            DatasetSelection(asset="BTC", timeframe="1d", file="btc.csv",
                             start_date="2022-01-01", end_date="2023-01-01"),
            DatasetSelection(asset="ETH", timeframe="4h", file="eth.csv",
                             start_date="2024-01-01", end_date="2025-01-01"),
        ],
    )
    plan = generate_plan(config)
    assets = {run.asset for run in plan}
    assert assets == {"BTC", "ETH"}
    # Each dataset gets the same number of signal combos
    btc_count = sum(1 for r in plan if r.asset == "BTC")
    eth_count = sum(1 for r in plan if r.asset == "ETH")
    assert btc_count == eth_count


def test_compute_total_runs_matches_plan():
    config = _make_config()
    total = compute_total_runs(config)
    plan = generate_plan(config)
    assert total == len(plan)


def test_compute_total_runs_random():
    config = _make_config(search_mode="random", n_random=3)
    total = compute_total_runs(config)
    assert total == 3


def test_exit_signals_included():
    config = _make_config(
        exit_signals=SignalSelection(
            triggers=[SignalConfig(
                name="rsi_cross_up", signal_type="TRIGGER",
                params_sweep={"threshold": ParamSweep(values=[50, 60])},
            )],
            filters=[],
        ),
    )
    plan = generate_plan(config)
    for run in plan:
        exit_sigs = json.loads(run.exit_json)
        if run.num_exit_signals > 0:
            assert exit_sigs[0]["name"] == "rsi_cross_up"
