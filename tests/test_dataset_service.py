"""Tests for dataset discovery service."""

import os
import tempfile

from experiment_server.services.dataset import compute_file_hash, discover_datasets


def test_discover_datasets_finds_matching_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "btc_2022-08-01_2026-02-15_1d.csv")
        with open(path, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2022-08-01,23000,24000,22000,23500,1000\n")

        datasets = discover_datasets(tmpdir)
        assert len(datasets) == 1
        assert datasets[0].asset == "BTC"
        assert datasets[0].timeframe == "1d"
        assert datasets[0].start_date == "2022-08-01"
        assert datasets[0].end_date == "2026-02-15"
        assert datasets[0].rows == 1
        assert datasets[0].file == "btc_2022-08-01_2026-02-15_1d.csv"


def test_discover_datasets_ignores_invalid_filenames():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Valid
        with open(os.path.join(tmpdir, "eth_2024-01-01_2026-02-01_4h.csv"), "w") as f:
            f.write("header\nrow1\nrow2\n")
        # Invalid: no dates
        with open(os.path.join(tmpdir, "random_data.csv"), "w") as f:
            f.write("header\n")
        # Invalid: bad timeframe
        with open(os.path.join(tmpdir, "btc_2022-01-01_2023-01-01_hourly.csv"), "w") as f:
            f.write("header\n")

        datasets = discover_datasets(tmpdir)
        assert len(datasets) == 1
        assert datasets[0].asset == "ETH"


def test_discover_datasets_returns_sorted():
    with tempfile.TemporaryDirectory() as tmpdir:
        for name in [
            "sol_2026-02-01_2026-02-16_5m.csv",
            "btc_2022-08-01_2026-02-15_1d.csv",
            "eth_2024-01-01_2026-02-01_4h.csv",
        ]:
            with open(os.path.join(tmpdir, name), "w") as f:
                f.write("header\n")

        datasets = discover_datasets(tmpdir)
        assets = [d.asset for d in datasets]
        assert assets == ["BTC", "ETH", "SOL"]


def test_discover_datasets_empty_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        datasets = discover_datasets(tmpdir)
        assert datasets == []


def test_discover_datasets_nonexistent_dir():
    datasets = discover_datasets("/nonexistent/path")
    assert datasets == []


def test_compute_file_hash_deterministic():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("test data\n")
        path = f.name

    h1 = compute_file_hash(path)
    h2 = compute_file_hash(path)
    assert h1 == h2
    assert h1.startswith("sha256:")
    assert len(h1) == 71  # "sha256:" + 64 hex chars
    os.unlink(path)


def test_compute_file_hash_different_content():
    paths = []
    for content in ["data1\n", "data2\n"]:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(content)
            paths.append(f.name)

    h1 = compute_file_hash(paths[0])
    h2 = compute_file_hash(paths[1])
    assert h1 != h2

    for p in paths:
        os.unlink(p)
