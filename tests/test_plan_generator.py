"""Tests for the dual-mode plan generator."""

import json
import os

from experiment_server.models.experiment import (
    DatasetSelection,
    ExecConfigSweep,
    ExperimentConfig,
    GridSignalConfig,
    ParamSweep,
    RandomSignalConfig,
    SignalConfig,
    SignalSelection,
)
from experiment_server.services.plan_generator import (
    apply_constraints,
    compute_total_runs,
    expand_param_sweep,
    generate_exec_config_variants,
    generate_plan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ds():
    return DatasetSelection(
        asset="BTC", timeframe="1d", file="btc.csv",
        start_date="2022-08-01", end_date="2026-02-15",
    )

def _trigger(values_fast=None, values_slow=None):
    return SignalConfig(
        name="ema_cross_up", signal_type="TRIGGER", timeframe="1d",
        params_sweep={
            "window_fast": ParamSweep(values=values_fast or [9, 15]),
            "window_slow": ParamSweep(values=values_slow or [21, 50]),
        },
    )

def _filter():
    return SignalConfig(
        name="rsi_oversold", signal_type="FILTER", timeframe="1d",
        params_sweep={
            "window": ParamSweep(values=[14]),
            "threshold": ParamSweep(values=[25, 30]),
        },
    )

def _grid_config(**kw):
    defaults = dict(
        name="test", seed=42, search_mode="grid",
        datasets=[_ds()],
        entry_signals=SignalSelection(triggers=[_trigger()], filters=[_filter()]),
        execution_config=ExecConfigSweep(base={"reward_factor": 2.0}),
        grid_signals=GridSignalConfig(n_param_combos=10),
    )
    defaults.update(kw)
    return ExperimentConfig(**defaults)


# ---------------------------------------------------------------------------
# expand_param_sweep
# ---------------------------------------------------------------------------

def test_expand_explicit_values():
    assert expand_param_sweep(ParamSweep(values=[1.5, 2.0, 3.0])) == [1.5, 2.0, 3.0]

def test_expand_range_int():
    assert expand_param_sweep(ParamSweep(min=0, max=6, step=2)) == [0, 2, 4, 6]

def test_expand_range_float():
    result = expand_param_sweep(ParamSweep(min=0.0, max=0.1, step=0.05))
    assert len(result) == 3

def test_expand_bool():
    assert expand_param_sweep(ParamSweep(values=[True, False])) == [True, False]


# ---------------------------------------------------------------------------
# constraints
# ---------------------------------------------------------------------------

def test_constraints_filter_invalid():
    combos = [
        {"window_fast": 5, "window_slow": 20},
        {"window_fast": 25, "window_slow": 20},
        {"window_fast": 10, "window_slow": 10},
    ]
    valid = apply_constraints(combos, [["window_fast", "<", "window_slow"]])
    assert len(valid) == 1
    assert valid[0]["window_fast"] == 5

def test_constraints_allow_overlap():
    combos = [
        {"window_fast": 25, "window_slow": 26},
        {"window_fast": 30, "window_slow": 50},
        {"window_fast": 50, "window_slow": 25},
        {"window_fast": 49, "window_slow": 50},
    ]
    assert len(apply_constraints(combos, [["window_fast", "<", "window_slow"]])) == 3


# ---------------------------------------------------------------------------
# exec config variants
# ---------------------------------------------------------------------------

def test_exec_no_sweep():
    ec = ExecConfigSweep(base={"reward_factor": 2.0, "cooldown_bars": 3})
    assert len(generate_exec_config_variants(ec)) == 1

def test_exec_cross_product():
    ec = ExecConfigSweep(
        base={"reward_factor": 2.0, "cooldown_bars": 3},
        sweep_axes=[
            {"param": "reward_factor", "values": [1.5, 2.0, 3.0]},
            {"param": "cooldown_bars", "values": [0, 3]},
        ],
    )
    assert len(generate_exec_config_variants(ec)) == 6


# ---------------------------------------------------------------------------
# Grid search
# ---------------------------------------------------------------------------

def test_grid_generates_correct_count():
    config = _grid_config()
    plan = generate_plan(config)
    # 1 trigger(2fast x 2slow=4 params) x 1 filter(1win x 2thresh=2 params) x 1 exec x 1 ds = 8
    assert len(plan) == 8

def test_grid_unique_indices():
    plan = generate_plan(_grid_config())
    indices = [r.run_index for r in plan]
    assert len(set(indices)) == len(indices)

def test_grid_with_exec_sweep():
    config = _grid_config(
        execution_config=ExecConfigSweep(
            base={"reward_factor": 2.0},
            sweep_axes=[{"param": "reward_factor", "values": [1.5, 3.0]}],
        ),
    )
    plan = generate_plan(config)
    # 8 signal combos x 2 exec variants = 16
    assert len(plan) == 16
    rfs = {r.exec_config["reward_factor"] for r in plan}
    assert rfs == {1.5, 3.0}

def test_grid_entry_json_valid():
    plan = generate_plan(_grid_config())
    for run in plan:
        entry = json.loads(run.entry_json)
        assert len(entry) >= 2
        assert entry[0]["signal_type"] == "TRIGGER"

def test_grid_multiple_datasets():
    config = _grid_config(datasets=[
        DatasetSelection(asset="BTC", timeframe="1d", file="btc.csv",
                         start_date="2022-01-01", end_date="2023-01-01"),
        DatasetSelection(asset="ETH", timeframe="4h", file="eth.csv",
                         start_date="2024-01-01", end_date="2025-01-01"),
    ])
    plan = generate_plan(config)
    assets = {r.asset for r in plan}
    assert assets == {"BTC", "ETH"}

def test_compute_total_matches_grid():
    config = _grid_config()
    assert compute_total_runs(config) == len(generate_plan(config))


# ---------------------------------------------------------------------------
# Random search
# ---------------------------------------------------------------------------

def test_random_respects_n():
    config = ExperimentConfig(
        name="test", seed=42, search_mode="random", n_random=50,
        datasets=[_ds()],
        random_signals=RandomSignalConfig(
            n_entry_triggers=1, min_entry_filters=1, max_entry_filters=2,
        ),
        execution_config=ExecConfigSweep(base={"reward_factor": 2.0}),
    )
    # Need signals_metadata.json to exist
    meta_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "signals_metadata.json",
    )
    if not os.path.exists(meta_path):
        return  # skip if no metadata file
    plan = generate_plan(config, metadata_path=meta_path)
    assert len(plan) == 50

def test_random_deterministic():
    config = ExperimentConfig(
        name="test", seed=42, search_mode="random", n_random=20,
        datasets=[_ds()],
        random_signals=RandomSignalConfig(),
        execution_config=ExecConfigSweep(base={"reward_factor": 2.0}),
    )
    meta_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "signals_metadata.json",
    )
    if not os.path.exists(meta_path):
        return
    plan1 = generate_plan(config, metadata_path=meta_path)
    plan2 = generate_plan(config, metadata_path=meta_path)
    assert [r.trigger_name for r in plan1] == [r.trigger_name for r in plan2]
    assert [r.entry_json for r in plan1] == [r.entry_json for r in plan2]

def test_random_has_variable_filters():
    config = ExperimentConfig(
        name="test", seed=123, search_mode="random", n_random=100,
        datasets=[_ds()],
        random_signals=RandomSignalConfig(
            min_entry_filters=1, max_entry_filters=3,
        ),
        execution_config=ExecConfigSweep(base={"reward_factor": 2.0}),
    )
    meta_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "signals_metadata.json",
    )
    if not os.path.exists(meta_path):
        return
    plan = generate_plan(config, metadata_path=meta_path)
    filter_counts = {r.num_entry_signals - 1 for r in plan}  # minus the trigger
    # With 100 runs and range 1-3, we should see at least 2 different counts
    assert len(filter_counts) >= 2

def test_random_compute_total():
    config = ExperimentConfig(
        name="test", seed=42, search_mode="random", n_random=500,
        datasets=[_ds(), DatasetSelection(
            asset="ETH", timeframe="4h", file="eth.csv",
            start_date="2024-01-01", end_date="2025-01-01",
        )],
        random_signals=RandomSignalConfig(),
        execution_config=ExecConfigSweep(base={}),
    )
    assert compute_total_runs(config) == 1000  # 500 x 2 datasets
