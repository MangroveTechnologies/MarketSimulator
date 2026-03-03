"""Deterministic run plan generator.

Two search modes:

Grid search:
  User selects specific signals and specifies param combos per signal.
  Every valid combination of signals x params x exec config is enumerated.

Random search:
  User specifies signal counts (e.g., 1 trigger, 1-3 filters) and N runs.
  Each run randomly picks signals from the full KB, randomly draws params
  from their KB ranges, and randomly samples an exec config variant.

Both modes produce a deterministic plan given the same config + seed.
"""

from __future__ import annotations

import json
import random as random_module
from dataclasses import dataclass, field
from itertools import product
from typing import Any

from experiment_server.models.experiment import (
    ExecConfigSweep,
    ExperimentConfig,
    ParamSweep,
    SignalConfig,
)


@dataclass
class RunSpec:
    """Specification for a single backtest run."""

    run_index: int
    dataset_key: str
    asset: str
    timeframe: str
    start_date: str
    end_date: str
    data_file: str
    entry_json: str
    exit_json: str
    trigger_name: str
    num_entry_signals: int
    num_exit_signals: int
    exec_config: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def expand_param_sweep(sweep: ParamSweep) -> list[Any]:
    """Expand a ParamSweep into concrete values."""
    if sweep.values is not None:
        return list(sweep.values)
    if sweep.min is None or sweep.max is None or sweep.step is None:
        if sweep.min is not None:
            return [sweep.min]
        return [0]
    values = []
    current = sweep.min
    while current <= sweep.max + 1e-9:  # float tolerance
        if isinstance(sweep.min, int) and isinstance(sweep.step, int):
            values.append(int(current))
        else:
            values.append(round(float(current), 6))
        current += sweep.step
    return values


def apply_constraints(
    combos: list[dict[str, Any]],
    constraints: list[list[str]],
) -> list[dict[str, Any]]:
    """Filter combinations that violate constraints."""
    if not constraints:
        return combos
    ops = {
        "<": lambda a, b: a < b, ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b,
        "!=": lambda a, b: a != b,
    }
    valid = []
    for combo in combos:
        ok = True
        for c in constraints:
            if len(c) != 3:
                continue
            a, op, b = c
            if a not in combo or b not in combo or op not in ops:
                continue
            if not ops[op](combo[a], combo[b]):
                ok = False
                break
        if ok:
            valid.append(combo)
    return valid


def _load_trading_defaults() -> dict[str, Any]:
    """Load and flatten trading_defaults.json into a single dict."""
    import json as json_mod
    from experiment_server.config import settings
    with open(settings.trading_defaults_path) as f:
        defaults = json_mod.load(f)
    flat = {}
    for section in ["risk_management", "position_limits", "volatility_settings",
                     "trading_rules", "time_based_exits", "backtest_defaults"]:
        flat.update(defaults.get(section, {}))
    return flat


def generate_exec_config_variants(ec: ExecConfigSweep) -> list[dict[str, Any]]:
    """Generate execution config variants from sweep axes (cross-product)."""
    # Start from trading defaults, overlay user-provided base on top.
    base = _load_trading_defaults()
    base.update(ec.base)
    if not ec.sweep_axes:
        return [base]

    param_names, param_values = [], []
    for axis in ec.sweep_axes:
        name = axis["param"]
        param_names.append(name)
        if "values" in axis:
            param_values.append(axis["values"])
        elif "min" in axis and "max" in axis and "step" in axis:
            sweep = ParamSweep(min=axis["min"], max=axis["max"], step=axis["step"])
            param_values.append(expand_param_sweep(sweep))
        else:
            param_values.append([base.get(name)])

    variants = []
    for combo in product(*param_values):
        v = dict(base)
        for name, val in zip(param_names, combo):
            v[name] = val
        variants.append(v)
    return variants


def _build_signal_object(name: str, sig_type: str, timeframe: str,
                         params: dict) -> dict:
    return {
        "name": name, "signal_type": sig_type,
        "timeframe": timeframe, "params": params,
    }


# ---------------------------------------------------------------------------
# Grid search
# ---------------------------------------------------------------------------

def _grid_signal_param_combos(sig: SignalConfig, n: int) -> list[dict]:
    """Generate up to n param combos for a signal via grid enumeration."""
    if not sig.params_sweep:
        return [{}]
    pnames = sorted(sig.params_sweep.keys())
    pvalues = [expand_param_sweep(sig.params_sweep[p]) for p in pnames]
    all_combos = [dict(zip(pnames, vals)) for vals in product(*pvalues)]
    if n >= len(all_combos):
        return all_combos
    # Evenly sample n from the full set
    import numpy as np
    indices = np.linspace(0, len(all_combos) - 1, n, dtype=int)
    return [all_combos[i] for i in indices]


def _generate_grid_plan(config: ExperimentConfig) -> list[RunSpec]:
    """Grid search: enumerate signals x params x exec config x datasets."""
    n_params = config.grid_signals.n_param_combos
    exec_variants = generate_exec_config_variants(config.execution_config)

    # Build entry combos: each trigger x each filter (with param combos)
    entry_combos = []
    constraints = config.entry_signals.constraints
    for trigger in config.entry_signals.triggers:
        t_combos = _grid_signal_param_combos(trigger, n_params)
        t_combos = apply_constraints(t_combos, constraints)
        for filt in config.entry_signals.filters:
            f_combos = _grid_signal_param_combos(filt, n_params)
            f_combos = apply_constraints(f_combos, constraints)
            for tp in t_combos:
                for fp in f_combos:
                    entry = [
                        _build_signal_object(trigger.name, "TRIGGER", trigger.timeframe, tp),
                        _build_signal_object(filt.name, "FILTER", filt.timeframe, fp),
                    ]
                    entry_combos.append((entry, trigger.name))

    # Build exit combos
    exit_combos = [[]]
    if config.exit_signals.triggers or config.exit_signals.filters:
        exit_combos = []
        for sig in config.exit_signals.triggers + config.exit_signals.filters:
            s_combos = _grid_signal_param_combos(sig, n_params)
            s_combos = apply_constraints(s_combos, config.exit_signals.constraints)
            for sp in s_combos:
                exit_combos.append([_build_signal_object(
                    sig.name, sig.signal_type, sig.timeframe, sp,
                )])
        if not exit_combos:
            exit_combos = [[]]

    runs = []
    idx = 0
    for ds in config.datasets:
        dk = f"{ds.asset}_{ds.timeframe}"
        for entry, trig_name in entry_combos:
            for exit_sigs in exit_combos:
                for ec in exec_variants:
                    runs.append(RunSpec(
                        run_index=idx, dataset_key=dk, asset=ds.asset,
                        timeframe=ds.timeframe, start_date=ds.start_date,
                        end_date=ds.end_date, data_file=ds.file,
                        entry_json=json.dumps(entry),
                        exit_json=json.dumps(exit_sigs),
                        trigger_name=trig_name,
                        num_entry_signals=len(entry),
                        num_exit_signals=len(exit_sigs),
                        exec_config=ec,
                    ))
                    idx += 1
    return runs


# ---------------------------------------------------------------------------
# Random search
# ---------------------------------------------------------------------------

def _load_signals_by_type(metadata_path: str) -> tuple[list[dict], list[dict]]:
    """Load triggers and filters from signals_metadata.json."""
    import json as json_mod
    from experiment_server.config import settings
    path = metadata_path or settings.signals_metadata_path
    with open(path) as f:
        metadata = json_mod.load(f)
    # Exclude pattern signals -- they use non-standard params (lookback)
    # and are not suitable for automated sweep.
    triggers = [{"name": n, **m} for n, m in metadata.items()
                if m.get("type") == "TRIGGER" and not m.get("disabled")
                and m.get("category") != "patterns"]
    filters = [{"name": n, **m} for n, m in metadata.items()
               if m.get("type") == "FILTER" and not m.get("disabled")
               and m.get("category") != "patterns"]
    return triggers, filters


def _random_params_for_signal(sig_meta: dict, rng: random_module.Random) -> dict:
    """Randomly draw parameter values from KB ranges for a signal."""
    params = {}
    for pname, pspec in sig_meta.get("params", {}).items():
        ptype = pspec.get("type", "float")
        pmin = pspec.get("min")
        pmax = pspec.get("max")
        default = pspec.get("default")

        if ptype in ("int", "integer") and pmin is not None and pmax is not None:
            params[pname] = rng.randint(int(pmin), int(pmax))
        elif ptype == "float" and pmin is not None and pmax is not None:
            params[pname] = round(rng.uniform(float(pmin), float(pmax)), 4)
        elif ptype == "bool":
            params[pname] = rng.choice([True, False])
        elif default is not None:
            params[pname] = default
    return params


def _passes_signal_constraints(sig_meta: dict, params: dict) -> bool:
    """Check if randomly drawn params satisfy signal constraints."""
    constraints = sig_meta.get("constraints", [])
    if not constraints:
        # Infer fast < slow constraint
        if "window_fast" in params and "window_slow" in params:
            constraints = [["window_fast", "<", "window_slow"]]
    ops = {"<": lambda a, b: a < b, ">": lambda a, b: a > b}
    for c in constraints:
        if len(c) != 3:
            continue
        a, op, b = c
        if a in params and b in params and op in ops:
            if not ops[op](params[a], params[b]):
                return False
    return True


def _generate_random_plan(
    config: ExperimentConfig,
    metadata_path: str | None = None,
) -> list[RunSpec]:
    """Random search: sample N runs with random signals, params, exec config."""
    rng = random_module.Random(config.seed)
    rc = config.random_signals
    triggers, filters = _load_signals_by_type(metadata_path)
    exec_variants = generate_exec_config_variants(config.execution_config)

    runs = []
    idx = 0
    n_per_dataset = config.n_random or 10000

    for ds in config.datasets:
        dk = f"{ds.asset}_{ds.timeframe}"

        for _ in range(n_per_dataset):
            # --- Entry signals ---
            # 1 trigger
            trig_meta = rng.choice(triggers)
            for attempt in range(20):
                trig_params = _random_params_for_signal(trig_meta, rng)
                if _passes_signal_constraints(trig_meta, trig_params):
                    break

            entry = [_build_signal_object(
                trig_meta["name"], "TRIGGER", ds.timeframe, trig_params,
            )]

            # 1-N filters
            n_filters = rng.randint(rc.min_entry_filters, rc.max_entry_filters)
            chosen_filters = rng.sample(filters, min(n_filters, len(filters)))
            for filt_meta in chosen_filters:
                for attempt in range(20):
                    filt_params = _random_params_for_signal(filt_meta, rng)
                    if _passes_signal_constraints(filt_meta, filt_params):
                        break
                entry.append(_build_signal_object(
                    filt_meta["name"], "FILTER", ds.timeframe, filt_params,
                ))

            # --- Exit signals ---
            # If an exit trigger is drawn, optionally add filters.
            # If no exit trigger, skip filters too (engine requires
            # exactly 1 trigger when any exit signals are present).
            exit_sigs = []
            n_exit_triggers = rng.randint(rc.min_exit_triggers, rc.max_exit_triggers)
            if n_exit_triggers > 0:
                exit_trig = rng.choice(triggers)
                for attempt in range(20):
                    ep = _random_params_for_signal(exit_trig, rng)
                    if _passes_signal_constraints(exit_trig, ep):
                        break
                exit_sigs.append(_build_signal_object(
                    exit_trig["name"], "TRIGGER", ds.timeframe, ep,
                ))

                n_exit_filters = rng.randint(rc.min_exit_filters, rc.max_exit_filters)
                if n_exit_filters > 0:
                    exit_filts = rng.sample(filters, min(n_exit_filters, len(filters)))
                    for ef_meta in exit_filts:
                        for attempt in range(20):
                            ep = _random_params_for_signal(ef_meta, rng)
                            if _passes_signal_constraints(ef_meta, ep):
                                break
                        exit_sigs.append(_build_signal_object(
                            ef_meta["name"], "FILTER", ds.timeframe, ep,
                        ))

            # --- Exec config ---
            ec = rng.choice(exec_variants)

            runs.append(RunSpec(
                run_index=idx, dataset_key=dk, asset=ds.asset,
                timeframe=ds.timeframe, start_date=ds.start_date,
                end_date=ds.end_date, data_file=ds.file,
                entry_json=json.dumps(entry),
                exit_json=json.dumps(exit_sigs),
                trigger_name=trig_meta["name"],
                num_entry_signals=len(entry),
                num_exit_signals=len(exit_sigs),
                exec_config=ec,
            ))
            idx += 1

    return runs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_plan(
    config: ExperimentConfig,
    metadata_path: str | None = None,
) -> list[RunSpec]:
    """Generate the complete run plan for an experiment.

    Grid mode: enumerates all signal x param x exec config combinations.
    Random mode: samples N runs with random signals, params, exec config.

    Same config + seed = identical plan every time.
    """
    if config.search_mode == "random":
        plan = _generate_random_plan(config, metadata_path)
    else:
        plan = _generate_grid_plan(config)

    # Shuffle for balanced worker distribution (deterministic)
    rng = random_module.Random(config.seed)
    rng.shuffle(plan)
    for i, run in enumerate(plan):
        run.run_index = i

    return plan


def compute_total_runs(config: ExperimentConfig) -> int:
    """Compute total run count without generating the full plan."""
    if config.search_mode == "random":
        n = config.n_random or 10000
        return n * len(config.datasets)

    # Grid: count the cross-product
    n_params = config.grid_signals.n_param_combos
    entry_count = 0
    for t in config.entry_signals.triggers:
        t_combos = len(_grid_signal_param_combos(t, n_params))
        for f in config.entry_signals.filters:
            f_combos = len(_grid_signal_param_combos(f, n_params))
            entry_count += t_combos * f_combos

    exit_count = 1
    if config.exit_signals.triggers or config.exit_signals.filters:
        exit_count = 0
        for s in config.exit_signals.triggers + config.exit_signals.filters:
            exit_count += len(_grid_signal_param_combos(s, n_params))
        exit_count = max(exit_count, 1)

    exec_count = len(generate_exec_config_variants(config.execution_config))
    ds_count = len(config.datasets)

    return ds_count * entry_count * exit_count * exec_count
