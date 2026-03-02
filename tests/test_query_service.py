"""Tests for the DuckDB query service."""

import json
import os
import tempfile

from experiment_server.services.query import count_completed, get_result_row, query_results
from experiment_server.workers.parquet_writer import ParquetChunkWriter


def _make_row(run_index: int, asset: str = "BTC", sharpe: float = 1.0,
              status: str = "ok", reward_factor: float = 2.0,
              total_trades: int = 10) -> dict:
    return {
        "experiment_id": "test_exp",
        "run_index": run_index,
        "config_hash": f"hash{run_index:04d}",
        "code_version": "abc",
        "rng_seed": 42,
        "data_file_path": "test.csv",
        "data_file_hash": "sha256:abc",
        "data_file_rows": 100,
        "strategy_name": f"strat_{run_index}",
        "asset": asset,
        "timeframe": "1d",
        "start_date": "2022-08-01",
        "end_date": "2026-02-15",
        "entry_json": "[]",
        "trigger_name": "ema_cross_up",
        "num_entry_signals": 1,
        "exit_json": "[]",
        "num_exit_signals": 0,
        "reward_factor": reward_factor,
        "max_risk_per_trade": 0.01,
        "stop_loss_calculation": "dynamic_atr",
        "atr_period": 14,
        "atr_volatility_factor": 2.0,
        "atr_short_weight": 0.7,
        "atr_long_weight": 0.3,
        "initial_balance": 10000.0,
        "min_balance_threshold": 0.1,
        "min_trade_amount": 25.0,
        "max_open_positions": 1,
        "max_trades_per_day": 5,
        "max_units_per_trade": 10000.0,
        "max_trade_amount": 10000000.0,
        "volatility_window": 24,
        "target_volatility": 0.02,
        "volatility_mode": "stddev",
        "enable_volatility_adj": False,
        "max_hold_time_hours": None,
        "cooldown_bars": 2,
        "daily_momentum_limit": 3.0,
        "weekly_momentum_limit": 3.0,
        "max_hold_bars": 100,
        "exit_on_loss_after_bars": 50,
        "exit_on_profit_after_bars": 100,
        "profit_threshold_pct": 0.04,
        "slippage_pct": 0.0075,
        "fee_pct": 0.0085,
        "total_trades": total_trades,
        "win_rate": 0.6,
        "total_return": 15.0 + run_index,
        "sharpe_ratio": sharpe,
        "sortino_ratio": 2.0,
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
        "net_pnl": 1500.0,
        "starting_balance_result": 10000.0,
        "ending_balance": 11500.0,
        "status": status,
        "error_msg": None,
        "elapsed_seconds": 3.0,
        "completed_at": "2026-02-28T14:30:00Z",
    }


def _write_test_data(exp_dir: str, n: int = 10) -> None:
    """Write n test rows to a Parquet file in the experiment directory."""
    results_dir = os.path.join(exp_dir, "results", "BTC_1d")
    os.makedirs(results_dir, exist_ok=True)
    writer = ParquetChunkWriter(output_dir=results_dir, worker_id=0, chunk_size=n + 1)
    for i in range(n):
        writer.add_row(_make_row(i, sharpe=float(n - i)))
    writer.close()


def test_query_results_returns_all():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=5)
        result = query_results(tmpdir)
        assert result["total"] == 5
        assert len(result["results"]) == 5


def test_query_results_sorted_desc():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=10)
        result = query_results(tmpdir, sort="sharpe_ratio", order="desc", limit=5)
        sharpes = [r["sharpe_ratio"] for r in result["results"]]
        assert sharpes == sorted(sharpes, reverse=True)
        assert len(result["results"]) == 5


def test_query_results_filter_by_asset():
    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = os.path.join(tmpdir, "results", "BTC_1d")
        os.makedirs(results_dir, exist_ok=True)
        writer = ParquetChunkWriter(output_dir=results_dir, worker_id=0, chunk_size=20)
        for i in range(5):
            writer.add_row(_make_row(i, asset="BTC"))
        for i in range(5, 10):
            writer.add_row(_make_row(i, asset="ETH"))
        writer.close()

        result = query_results(tmpdir, filters={"asset": "BTC"})
        assert result["total"] == 5
        assert all(r["asset"] == "BTC" for r in result["results"])


def test_query_results_min_trades():
    with tempfile.TemporaryDirectory() as tmpdir:
        results_dir = os.path.join(tmpdir, "results", "BTC_1d")
        os.makedirs(results_dir, exist_ok=True)
        writer = ParquetChunkWriter(output_dir=results_dir, worker_id=0, chunk_size=20)
        for i in range(10):
            writer.add_row(_make_row(i, total_trades=i * 5))
        writer.close()

        result = query_results(tmpdir, min_trades=20)
        assert all(r["total_trades"] >= 20 for r in result["results"])


def test_query_results_pagination():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=20)
        page1 = query_results(tmpdir, limit=5, offset=0)
        page2 = query_results(tmpdir, limit=5, offset=5)
        assert page1["total"] == 20
        assert len(page1["results"]) == 5
        assert len(page2["results"]) == 5
        # Pages should not overlap
        idx1 = {r["run_index"] for r in page1["results"]}
        idx2 = {r["run_index"] for r in page2["results"]}
        assert idx1.isdisjoint(idx2)


def test_query_empty_experiment():
    with tempfile.TemporaryDirectory() as tmpdir:
        result = query_results(tmpdir)
        assert result["total"] == 0
        assert result["results"] == []


def test_count_completed():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=15)
        completed = count_completed(tmpdir)
        assert len(completed) == 15
        assert 0 in completed
        assert 14 in completed


def test_count_completed_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        completed = count_completed(tmpdir)
        assert completed == set()


def test_get_result_row():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=5)
        row = get_result_row(tmpdir, run_index=2)
        assert row is not None
        assert row["run_index"] == 2
        assert row["asset"] == "BTC"


def test_get_result_row_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=5)
        row = get_result_row(tmpdir, run_index=999)
        assert row is None
