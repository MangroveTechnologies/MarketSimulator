"""Pydantic models for experiment configuration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ParamSweep(BaseModel):
    """Sweep definition for a single parameter.

    Either provide explicit values OR a min/max/step range.
    """

    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    values: list[float | int | str | bool] | None = None


class SignalConfig(BaseModel):
    """A signal selected for sweeping with its param sweep definitions.

    Used in grid mode where the user picks specific signals.
    """

    name: str
    signal_type: Literal["TRIGGER", "FILTER"]
    timeframe: str = "1h"
    params_sweep: dict[str, ParamSweep] = Field(default_factory=dict)


class SignalSelection(BaseModel):
    """Entry or exit signal configuration for an experiment.

    In grid mode: triggers and filters are explicit lists of SignalConfig.
    In random mode: triggers and filters are empty, and the counts below
    control how many are randomly drawn per run.
    """

    triggers: list[SignalConfig] = Field(default_factory=list)
    filters: list[SignalConfig] = Field(default_factory=list)
    min_filters: int = 1
    max_filters: int = 1
    constraints: list[list[str]] = Field(default_factory=list)


class RandomSignalConfig(BaseModel):
    """Signal count configuration for random search mode.

    Controls how many signals are randomly drawn per run.
    """

    n_entry_triggers: int = 1
    min_entry_filters: int = 1
    max_entry_filters: int = 2
    min_exit_triggers: int = 0
    max_exit_triggers: int = 1
    min_exit_filters: int = 0
    max_exit_filters: int = 2
    n_param_draws: int = 1  # params randomly drawn from KB ranges


class GridSignalConfig(BaseModel):
    """Signal config for grid search mode.

    Controls how many param combos per signal in grid enumeration.
    """

    n_param_combos: int = 3  # param combos per signal


class ExecConfigSweep(BaseModel):
    """Execution config with base values and optional sweep axes."""

    base: dict[str, Any] = Field(default_factory=dict)
    sweep_axes: list[dict[str, Any]] = Field(default_factory=list)


class DatasetSelection(BaseModel):
    """A selected OHLCV data file for the experiment."""

    asset: str
    timeframe: str
    file: str
    hash: str = ""
    rows: int = 0
    start_date: str
    end_date: str


class ExperimentConfig(BaseModel):
    """Full experiment configuration -- the top-level object.

    Two search modes:
    - grid: enumerate all signal combos x param combos x exec config variants
    - random: randomly sample N runs (signals, params, exec config all random)
    """

    experiment_id: str = ""
    name: str
    description: str = ""
    seed: int = 42
    search_mode: Literal["grid", "random"] = "grid"

    # Random mode settings
    n_random: int | None = None  # total runs per dataset
    random_signals: RandomSignalConfig = Field(default_factory=RandomSignalConfig)

    # Grid mode settings
    grid_signals: GridSignalConfig = Field(default_factory=GridSignalConfig)

    datasets: list[DatasetSelection]
    entry_signals: SignalSelection = Field(default_factory=SignalSelection)
    exit_signals: SignalSelection = Field(default_factory=SignalSelection)
    execution_config: ExecConfigSweep = Field(default_factory=ExecConfigSweep)
    workers_per_dataset: int = 2
    code_version: str = ""
    notes: str = ""
    status: str = "draft"
    created_at: str = ""
    total_runs: int | None = None
