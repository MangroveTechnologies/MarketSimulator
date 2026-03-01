"""Tests for experiment API endpoints."""

import tempfile

import pytest
from fastapi.testclient import TestClient

from experiment_server.app import create_app
from experiment_server.config import settings


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path):
    orig = settings.data_dir
    settings.data_dir = str(tmp_path)
    yield tmp_path
    settings.data_dir = orig


def _client():
    return TestClient(create_app())


def _valid_config():
    return {
        "name": "test_experiment",
        "seed": 42,
        "search_mode": "grid",
        "datasets": [{
            "asset": "BTC", "timeframe": "1d",
            "file": "btc_2022-08-01_2026-02-15_1d.csv",
            "start_date": "2022-08-01", "end_date": "2026-02-15",
        }],
        "entry_signals": {
            "triggers": [{
                "name": "ema_cross_up", "signal_type": "TRIGGER",
                "params_sweep": {
                    "window_fast": {"values": [9]},
                    "window_slow": {"values": [21]},
                },
            }],
            "filters": [{
                "name": "rsi_oversold", "signal_type": "FILTER",
                "params_sweep": {
                    "window": {"values": [14]},
                    "threshold": {"values": [30]},
                },
            }],
        },
        "execution_config": {
            "base": {"reward_factor": 2.0},
        },
    }


def test_create_experiment():
    client = _client()
    resp = client.post("/api/v1/experiments", json=_valid_config())
    assert resp.status_code == 201
    data = resp.json()
    assert "experiment_id" in data
    assert data["status"] == "draft"


def test_list_experiments():
    client = _client()
    client.post("/api/v1/experiments", json=_valid_config())
    client.post("/api/v1/experiments", json=_valid_config())

    resp = client.get("/api/v1/experiments")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


def test_get_experiment():
    client = _client()
    create_resp = client.post("/api/v1/experiments", json=_valid_config())
    exp_id = create_resp.json()["experiment_id"]

    resp = client.get(f"/api/v1/experiments/{exp_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "test_experiment"


def test_get_nonexistent():
    client = _client()
    resp = client.get("/api/v1/experiments/nonexistent")
    assert resp.status_code == 404


def test_delete_experiment():
    client = _client()
    create_resp = client.post("/api/v1/experiments", json=_valid_config())
    exp_id = create_resp.json()["experiment_id"]

    resp = client.delete(f"/api/v1/experiments/{exp_id}")
    assert resp.status_code == 200

    resp = client.get(f"/api/v1/experiments/{exp_id}")
    assert resp.status_code == 404


def test_validate_experiment():
    client = _client()
    create_resp = client.post("/api/v1/experiments", json=_valid_config())
    exp_id = create_resp.json()["experiment_id"]

    resp = client.post(f"/api/v1/experiments/{exp_id}/validate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["total_runs"] > 0


def test_validate_invalid_experiment():
    client = _client()
    config = _valid_config()
    config["datasets"] = []
    create_resp = client.post("/api/v1/experiments", json=config)
    exp_id = create_resp.json()["experiment_id"]

    resp = client.post(f"/api/v1/experiments/{exp_id}/validate")
    assert resp.status_code == 400


def test_launch_requires_validation():
    client = _client()
    create_resp = client.post("/api/v1/experiments", json=_valid_config())
    exp_id = create_resp.json()["experiment_id"]

    resp = client.post(f"/api/v1/experiments/{exp_id}/launch")
    assert resp.status_code == 400
    assert "validated" in resp.json()["detail"].lower()
