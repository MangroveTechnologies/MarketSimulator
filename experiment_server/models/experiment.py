"""Pydantic models for experiment configuration."""

from __future__ import annotations

from datetime import datetime
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
    """A signal selected for sweeping with its param sweep definitions."""

    name: str
    signal_type: Literal["TRIGGER", "FILTER"]
    timeframe: str = "1h"
    params_sweep: dict[str, ParamSweep] = Field(default_factory=dict)


class SignalSelection(BaseModel):
    """Entry or exit signal configuration for an experiment."""

    triggers: list[SignalConfig] = Field(default_factory=list)
    filters: list[SignalConfig] = Field(default_factory=list)
    min_filters: int = 1
    max_filters: int = 1
    constraints: list[list[str]] = Field(default_factory=list)


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
    """Full experiment configuration -- the top-level object."""

    experiment_id: str = ""
    name: str
    description: str = ""
    seed: int = 42
    search_mode: Literal["grid", "random"] = "grid"
    n_random: int | None = None
    datasets: list[DatasetSelection]
    entry_signals: SignalSelection
    exit_signals: SignalSelection = Field(default_factory=SignalSelection)
    execution_config: ExecConfigSweep
    workers_per_dataset: int = 2
    code_version: str = ""
    notes: str = ""
    status: str = "draft"
    created_at: str = ""
    total_runs: int | None = None
