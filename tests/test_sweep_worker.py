"""Tests for the sweep worker using a mock backtest function."""

import json
import os
import tempfile

import duckdb

from experiment_server.services.plan_generator import RunSpec
from experiment_server.workers.sweep_worker import execute_sweep_job


def _mock_backtest(strategy_config: dict, run: RunSpec) -> dict:
    """Fake backtest that returns fixed metrics."""
    return {
        "success": True,
        "metrics": {
            "total_trades": 10,
            "win_rate": 0.6,
            "annual_return": 15.0,
            "sharpe_ratio": 1.8,
            "sortino_ratio": 2.1,
            "max_drawdown": 5.0,
            "max_drawdown_duration": 10,
            "calmar_ratio": 3.0,
            "gain_to_pain_ratio": 2.5,
            "irr_annualized": 12.0,
            "irr_daily": 0.03,
            "avg_daily_return": 0.04,
            "max_consecutive_wins": 5,
            "max_consecutive_losses": 2,
            "num_days": 365,
            "starting_balance": 10000,
            "ending_balance": 11500,
        },
    }


def _mock_backtest_error(strategy_config: dict, run: RunSpec) -> dict:
    return {"success": False, "error": "test error"}


def _make_runs(n: int) -> list[RunSpec]:
    return [
        RunSpec(
            run_index=i,
            dataset_key="BTC_1d",
            asset="BTC",
            timeframe="1d",
            start_date="2022-08-01",
            end_date="2026-02-15",
            data_file="btc.csv",
            entry_json=json.dumps([
                {"name": "ema_cross_up", "signal_type": "TRIGGER",
                 "timeframe": "1d", "params": {"window_fast": 9, "window_slow": 21}},
                {"name": "rsi_oversold", "signal_type": "FILTER",
                 "timeframe": "1d", "params": {"window": 14, "threshold": 30}},
            ]),
            exit_json="[]",
            trigger_name="ema_cross_up",
            num_entry_signals=2,
            num_exit_signals=0,
            exec_config={
                "reward_factor": 2.0,
                "max_risk_per_trade": 0.01,
                "stop_loss_calculation": "dynamic_atr",
                "atr_period": 14,
                "atr_volatility_factor": 2.0,
                "atr_short_weight": 0.7,
                "atr_long_weight": 0.3,
                "initial_balance": 10000,
                "min_balance_threshold": 0.1,
                "min_trade_amount": 25,
                "max_open_positions": 1,
                "max_trades_per_day": 5,
                "max_units_per_trade": 10000,
                "max_trade_amount": 10000000,
                "volatility_window": 24,
                "target_volatility": 0.02,
                "volatility_mode": "stddev",
                "enable_volatility_adjustment": False,
                "max_hold_time_hours": None,
                "cooldown_bars": 2,
                "daily_momentum_limit": 3,
                "weekly_momentum_limit": 3,
                "max_hold_bars": 100,
                "exit_on_loss_after_bars": 50,
                "exit_on_profit_after_bars": 100,
                "profit_threshold_pct": 0.04,
                "slippage_pct": 0.0075,
                "fee_pct": 0.0085,
            },
        )
        for i in range(n)
    ]


def test_worker_writes_parquet():
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = _make_runs(5)
        result = execute_sweep_job(
            experiment_id="test_exp",
            experiment_dir=tmpdir,
            dataset_key="BTC_1d",
            worker_id=0,
            runs=[r.__dict__ for r in runs],
            experiment_config={"name": "test"},
            backtest_fn=_mock_backtest,
            chunk_size=10,
        )

        assert result["completed"] == 5
        assert result["errors"] == 0
        assert result["skipped"] == 0

        # Verify Parquet output
        parquet_dir = os.path.join(tmpdir, "results", "BTC_1d")
        files = [f for f in os.listdir(parquet_dir) if f.endswith(".parquet")]
        assert len(files) == 1

        conn = duckdb.connect()
        df = conn.execute(
            f"SELECT * FROM read_parquet('{parquet_dir}/*.parquet') ORDER BY run_index"
        ).fetchdf()
        conn.close()

        assert len(df) == 5
        assert list(df["run_index"]) == [0, 1, 2, 3, 4]
        assert df["experiment_id"].iloc[0] == "test_exp"
        assert df["trigger_name"].iloc[0] == "ema_cross_up"
        assert df["status"].iloc[0] == "ok"
        assert df["total_trades"].iloc[0] == 10


def test_worker_handles_errors():
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = _make_runs(3)
        result = execute_sweep_job(
            experiment_id="test_exp",
            experiment_dir=tmpdir,
            dataset_key="BTC_1d",
            worker_id=0,
            runs=[r.__dict__ for r in runs],
            experiment_config={"name": "test"},
            backtest_fn=_mock_backtest_error,
            chunk_size=10,
        )

        assert result["completed"] == 0
        assert result["errors"] == 3

        parquet_dir = os.path.join(tmpdir, "results", "BTC_1d")
        conn = duckdb.connect()
        df = conn.execute(
            f"SELECT status, error_msg FROM read_parquet('{parquet_dir}/*.parquet')"
        ).fetchdf()
        conn.close()

        assert all(df["status"] == "error")
        assert all("test error" in str(e) for e in df["error_msg"])


def test_worker_resumes_skipping_completed():
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = _make_runs(5)

        # First run: complete all 5
        execute_sweep_job(
            experiment_id="test_exp",
            experiment_dir=tmpdir,
            dataset_key="BTC_1d",
            worker_id=0,
            runs=[r.__dict__ for r in runs],
            experiment_config={"name": "test"},
            backtest_fn=_mock_backtest,
            chunk_size=10,
        )

        # Second run: same runs, should skip all
        result = execute_sweep_job(
            experiment_id="test_exp",
            experiment_dir=tmpdir,
            dataset_key="BTC_1d",
            worker_id=1,  # different worker
            runs=[r.__dict__ for r in runs],
            experiment_config={"name": "test"},
            backtest_fn=_mock_backtest,
            chunk_size=10,
        )

        assert result["skipped"] == 5
        assert result["completed"] == 0


def test_worker_multiple_chunks():
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = _make_runs(10)
        execute_sweep_job(
            experiment_id="test_exp",
            experiment_dir=tmpdir,
            dataset_key="BTC_1d",
            worker_id=0,
            runs=[r.__dict__ for r in runs],
            experiment_config={"name": "test"},
            backtest_fn=_mock_backtest,
            chunk_size=3,
        )

        parquet_dir = os.path.join(tmpdir, "results", "BTC_1d")
        files = sorted(f for f in os.listdir(parquet_dir) if f.endswith(".parquet"))
        assert len(files) == 4  # 3 + 3 + 3 + 1


def test_worker_provenance_fields():
    with tempfile.TemporaryDirectory() as tmpdir:
        runs = _make_runs(1)
        execute_sweep_job(
            experiment_id="test_exp",
            experiment_dir=tmpdir,
            dataset_key="BTC_1d",
            worker_id=0,
            runs=[r.__dict__ for r in runs],
            experiment_config={"name": "test"},
            experiment_seed=42,
            code_version="abc123",
            backtest_fn=_mock_backtest,
            chunk_size=10,
        )

        parquet_dir = os.path.join(tmpdir, "results", "BTC_1d")
        conn = duckdb.connect()
        df = conn.execute(
            f"SELECT code_version, rng_seed, data_file_path FROM read_parquet('{parquet_dir}/*.parquet')"
        ).fetchdf()
        conn.close()

        assert df["code_version"].iloc[0] == "abc123"
        assert df["rng_seed"].iloc[0] == 42000000  # seed * 1000000 + run_index(0)
        assert df["data_file_path"].iloc[0] == "btc.csv"
