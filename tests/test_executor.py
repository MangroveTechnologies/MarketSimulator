"""Tests for the executor service."""

import json
import os
import tempfile

from unittest.mock import patch

from experiment_server.config import settings
from experiment_server.models.experiment import (
    DatasetSelection,
    ExecConfigSweep,
    ExperimentConfig,
    ParamSweep,
    SignalConfig,
    SignalSelection,
)
from experiment_server.services.executor import (
    create_experiment,
    delete_experiment,
    get_experiment,
    launch_experiment,
    list_experiments,
    pause_experiment,
    validate_experiment,
)


def _make_config() -> ExperimentConfig:
    return ExperimentConfig(
        name="test_experiment",
        seed=42,
        search_mode="grid",
        datasets=[
            DatasetSelection(
                asset="BTC", timeframe="1d", file="btc_2022-08-01_2026-02-15_1d.csv",
                start_date="2022-08-01", end_date="2026-02-15",
            ),
        ],
        entry_signals=SignalSelection(
            triggers=[SignalConfig(
                name="ema_cross_up", signal_type="TRIGGER",
                params_sweep={"window_fast": ParamSweep(values=[9]), "window_slow": ParamSweep(values=[21])},
            )],
            filters=[SignalConfig(
                name="rsi_oversold", signal_type="FILTER",
                params_sweep={"window": ParamSweep(values=[14]), "threshold": ParamSweep(values=[30])},
            )],
        ),
        execution_config=ExecConfigSweep(base={"reward_factor": 2.0}),
    )


class TestExecutorCRUD:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig = settings.data_dir
        settings.data_dir = self._tmpdir

    def teardown_method(self):
        settings.data_dir = self._orig
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_create_experiment(self):
        config = _make_config()
        result = create_experiment(config)
        assert result.experiment_id.startswith("exp_")
        assert result.status == "draft"
        assert result.created_at != ""

    def test_get_experiment(self):
        config = _make_config()
        created = create_experiment(config)
        loaded = get_experiment(created.experiment_id)
        assert loaded is not None
        assert loaded.name == "test_experiment"
        assert loaded.experiment_id == created.experiment_id

    def test_get_nonexistent(self):
        assert get_experiment("nonexistent") is None

    def test_list_experiments(self):
        create_experiment(_make_config())
        create_experiment(_make_config())
        experiments = list_experiments()
        assert len(experiments) >= 2

    def test_delete_experiment(self):
        created = create_experiment(_make_config())
        exp_id = created.experiment_id
        delete_experiment(exp_id)
        assert get_experiment(exp_id) is None


class TestExecutorLifecycle:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_data = settings.data_dir
        self._orig_mangrove = settings.mangrove_data_dir
        settings.data_dir = self._tmpdir
        settings.mangrove_data_dir = self._tmpdir  # point to same dir for testing

    def teardown_method(self):
        settings.data_dir = self._orig_data
        settings.mangrove_data_dir = self._orig_mangrove
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_validate_valid_experiment(self):
        created = create_experiment(_make_config())
        result = validate_experiment(created.experiment_id)
        assert result["valid"] is True
        assert result["total_runs"] > 0
        assert result["errors"] == []

        # Config should be updated to validated
        loaded = get_experiment(created.experiment_id)
        assert loaded.status == "validated"

    def test_validate_no_datasets(self):
        config = _make_config()
        config.datasets = []
        created = create_experiment(config)
        result = validate_experiment(created.experiment_id)
        assert result["valid"] is False
        assert any("dataset" in e.lower() for e in result["errors"])

    def test_validate_no_triggers(self):
        config = _make_config()
        config.entry_signals.triggers = []
        created = create_experiment(config)
        result = validate_experiment(created.experiment_id)
        assert result["valid"] is False

    def test_launch_enqueues_jobs(self):
        created = create_experiment(_make_config())
        validate_experiment(created.experiment_id)

        enqueued = []
        result = launch_experiment(
            created.experiment_id,
            enqueue_fn=lambda job: enqueued.append(job),
        )

        assert result["status"] == "running"
        assert result["workers"] > 0
        assert result["total_runs"] > 0
        assert len(enqueued) > 0

        # Each job has the expected fields
        job = enqueued[0]
        assert job["experiment_id"] == created.experiment_id
        assert job["dataset_key"] == "BTC_1d"
        assert len(job["runs"]) > 0

    def test_launch_updates_status(self):
        created = create_experiment(_make_config())
        validate_experiment(created.experiment_id)
        launch_experiment(created.experiment_id, enqueue_fn=lambda j: None)

        loaded = get_experiment(created.experiment_id)
        assert loaded.status == "running"

    def test_launch_rejects_draft(self):
        created = create_experiment(_make_config())
        try:
            launch_experiment(created.experiment_id, enqueue_fn=lambda j: None)
            assert False, "Should have raised"
        except ValueError as e:
            assert "validated" in str(e).lower()
