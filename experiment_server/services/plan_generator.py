"""Deterministic run plan generator.

Takes an ExperimentConfig and produces an ordered list of RunSpec objects,
each describing a single backtest to execute. Supports grid search (enumerate
all combinations) and random search (sample N from the space).

Constraints (e.g., window_fast < window_slow) are enforced at generation time
by filtering invalid combinations after expansion.

Same config + same seed = identical plan, byte-for-byte. This is critical
for deterministic resume.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from itertools import product
from typing import Any

from experiment_server.models.experiment import (
    ExecConfigSweep,
    ExperimentConfig,
    ParamSweep,
    SignalConfig,
    SignalSelection,
)


@dataclass
class RunSpec:
    """Specification for a single backtest run.

    Contains everything needed to build the strategy config and execute
    the backtest. The run_index is the globally unique identifier within
    an experiment.
    """

    run_index: int
    dataset_key: str  # e.g., "BTC_1d"
    asset: str
    timeframe: str
    start_date: str
    end_date: str
    data_file: str
    entry_json: str  # JSON array of signal objects
    exit_json: str  # JSON array of signal objects
    trigger_name: str
    num_entry_signals: int
    num_exit_signals: int
    exec_config: dict[str, Any] = field(default_factory=dict)


def expand_param_sweep(sweep: ParamSweep) -> list[Any]:
    """Expand a ParamSweep into a list of concrete values.

    If explicit values are provided, use those.
    Otherwise, generate values from min/max/step.
    """
    if sweep.values is not None:
        return list(sweep.values)

    if sweep.min is None or sweep.max is None or sweep.step is None:
        # No sweep defined -- use min as single value, or 0
        if sweep.min is not None:
            return [sweep.min]
        return [0]

    values = []
    current = sweep.min
    while current <= sweep.max:
        # Preserve int type if all inputs are int
        if isinstance(sweep.min, int) and isinstance(sweep.step, int):
            values.append(int(current))
        else:
            values.append(round(float(current), 6))
        current += sweep.step

    return values


def generate_signal_param_combos(
    signal: SignalConfig,
) -> list[dict[str, Any]]:
    """Generate all parameter combinations for a signal.

    Returns a list of dicts, each mapping param_name -> concrete_value.
    If no params are swept, returns a single empty dict.
    """
    if not signal.params_sweep:
        return [{}]

    param_names = sorted(signal.params_sweep.keys())
    param_values = [expand_param_sweep(signal.params_sweep[p]) for p in param_names]

    combos = []
    for values in product(*param_values):
        combos.append(dict(zip(param_names, values)))

    return combos


def apply_constraints(
    combos: list[dict[str, Any]],
    constraints: list[list[str]],
) -> list[dict[str, Any]]:
    """Filter combinations that violate constraints.

    Each constraint is [param_a, operator, param_b] where operator is
    "<", ">", "<=", ">=", or "!=".
    """
    if not constraints:
        return combos

    ops = {
        "<": lambda a, b: a < b,
        ">": lambda a, b: a > b,
        "<=": lambda a, b: a <= b,
        ">=": lambda a, b: a >= b,
        "!=": lambda a, b: a != b,
    }

    valid = []
    for combo in combos:
        ok = True
        for constraint in constraints:
            if len(constraint) != 3:
                continue
            param_a, op, param_b = constraint
            if param_a not in combo or param_b not in combo:
                continue
            if op not in ops:
                continue
            if not ops[op](combo[param_a], combo[param_b]):
                ok = False
                break
        if ok:
            valid.append(combo)

    return valid


def _build_signal_object(
    signal: SignalConfig,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Build a signal dict for the strategy config entry/exit array."""
    return {
        "name": signal.name,
        "signal_type": signal.signal_type,
        "timeframe": signal.timeframe,
        "params": params,
    }


def generate_exec_config_variants(
    exec_config: ExecConfigSweep,
) -> list[dict[str, Any]]:
    """Generate execution config variants from sweep axes.

    Each variant is a complete exec config dict (base + overrides).
    If no sweep axes, returns [base_config].
    """
    base = dict(exec_config.base)

    if not exec_config.sweep_axes:
        return [base]

    # Build value lists per swept param
    param_names = []
    param_values = []
    for axis in exec_config.sweep_axes:
        name = axis["param"]
        param_names.append(name)
        if "values" in axis:
            param_values.append(axis["values"])
        elif "min" in axis and "max" in axis and "step" in axis:
            sweep = ParamSweep(
                min=axis["min"], max=axis["max"], step=axis["step"],
            )
            param_values.append(expand_param_sweep(sweep))
        else:
            param_values.append([base.get(name)])

    # Full cross-product of sweep axes
    variants = []
    for combo in product(*param_values):
        variant = dict(base)
        for name, value in zip(param_names, combo):
            variant[name] = value
        variants.append(variant)

    return variants


def _generate_entry_combos(
    signals: SignalSelection,
) -> list[tuple[list[dict], str]]:
    """Generate all entry signal combinations.

    Returns list of (entry_signal_list, trigger_name) tuples.
    Each entry_signal_list is a list of signal dicts ready for JSON serialization.
    """
    if not signals.triggers or not signals.filters:
        return []

    results = []

    for trigger in signals.triggers:
        trigger_combos = generate_signal_param_combos(trigger)
        trigger_combos = apply_constraints(trigger_combos, signals.constraints)

        for filter_sig in signals.filters:
            filter_combos = generate_signal_param_combos(filter_sig)
            filter_combos = apply_constraints(filter_combos, signals.constraints)

            for t_params in trigger_combos:
                for f_params in filter_combos:
                    entry = [
                        _build_signal_object(trigger, t_params),
                        _build_signal_object(filter_sig, f_params),
                    ]
                    results.append((entry, trigger.name))

    return results


def _generate_exit_combos(
    signals: SignalSelection,
) -> list[list[dict]]:
    """Generate all exit signal combinations.

    If no exit signals configured, returns [[]] (one combo: empty exit list).
    """
    if not signals.triggers and not signals.filters:
        return [[]]

    results = []
    all_exit_signals = signals.triggers + signals.filters

    for sig in all_exit_signals:
        combos = generate_signal_param_combos(sig)
        combos = apply_constraints(combos, signals.constraints)
        for params in combos:
            results.append([_build_signal_object(sig, params)])

    return results if results else [[]]


def generate_plan(config: ExperimentConfig) -> list[RunSpec]:
    """Generate the complete, deterministic run plan for an experiment.

    Args:
        config: The full experiment configuration.

    Returns:
        List of RunSpec objects, each with a unique run_index.
        Same config + seed = identical list every time.
    """
    entry_combos = _generate_entry_combos(config.entry_signals)
    exit_combos = _generate_exit_combos(config.exit_signals)
    exec_variants = generate_exec_config_variants(config.execution_config)

    all_runs: list[RunSpec] = []
    run_index = 0

    for dataset in config.datasets:
        dataset_key = f"{dataset.asset}_{dataset.timeframe}"

        for entry_signals, trigger_name in entry_combos:
            for exit_signals in exit_combos:
                for exec_config in exec_variants:
                    all_runs.append(RunSpec(
                        run_index=run_index,
                        dataset_key=dataset_key,
                        asset=dataset.asset,
                        timeframe=dataset.timeframe,
                        start_date=dataset.start_date,
                        end_date=dataset.end_date,
                        data_file=dataset.file,
                        entry_json=json.dumps(entry_signals),
                        exit_json=json.dumps(exit_signals),
                        trigger_name=trigger_name,
                        num_entry_signals=len(entry_signals),
                        num_exit_signals=len(exit_signals),
                        exec_config=exec_config,
                    ))
                    run_index += 1

    if config.search_mode == "random" and config.n_random is not None:
        # Deterministic random sampling
        rng = random.Random(config.seed)
        if config.n_random < len(all_runs):
            all_runs = rng.sample(all_runs, config.n_random)
            # Re-assign sequential run_index after sampling
            for i, run in enumerate(all_runs):
                run.run_index = i

    # Shuffle per-dataset for balanced worker distribution
    rng = random.Random(config.seed)
    rng.shuffle(all_runs)
    # Re-assign sequential run_index after shuffle
    for i, run in enumerate(all_runs):
        run.run_index = i

    return all_runs


def compute_total_runs(config: ExperimentConfig) -> int:
    """Compute the total number of runs without generating the full plan.

    Faster than len(generate_plan(config)) for validation display.
    """
    entry_count = len(_generate_entry_combos(config.entry_signals))
    exit_count = len(_generate_exit_combos(config.exit_signals))
    exec_count = len(generate_exec_config_variants(config.execution_config))
    dataset_count = len(config.datasets)

    total = dataset_count * entry_count * exit_count * exec_count

    if config.search_mode == "random" and config.n_random is not None:
        return min(total, config.n_random)

    return total
