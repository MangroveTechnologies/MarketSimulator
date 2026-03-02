"""Tests for the Parquet chunk writer."""

import json
import os
import tempfile

import duckdb

from experiment_server.workers.parquet_writer import RESULT_SCHEMA, ParquetChunkWriter


def _make_test_row(run_index: int, asset: str = "BTC") -> dict:
    """Build a complete test row with all 67 columns."""
    return {
        "experiment_id": "test_exp",
        "run_index": run_index,
        "config_hash": f"testhash{run_index:04d}",
        "code_version": "abc123",
        "rng_seed": 42,
        "data_file_path": "test.csv",
        "data_file_hash": "sha256:abc",
        "data_file_rows": 100,
        "strategy_name": f"test_strategy_{run_index}",
        "asset": asset,
        "timeframe": "1d",
        "start_date": "2022-08-01",
        "end_date": "2026-02-15",
        "entry_json": json.dumps([
            {"name": "ema_cross_up", "signal_type": "TRIGGER",
             "timeframe": "1d", "params": {"window_fast": 9, "window_slow": 21}},
        ]),
        "trigger_name": "ema_cross_up",
        "num_entry_signals": 1,
        "exit_json": "[]",
        "num_exit_signals": 0,
        "reward_factor": 2.0,
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
        "total_trades": 10 + run_index,
        "win_rate": 0.6,
        "total_return": 15.5 + run_index,
        "sharpe_ratio": 1.8 + run_index * 0.1,
        "sortino_ratio": 2.1,
        "max_drawdown": 5.2,
        "max_drawdown_duration": 12,
        "calmar_ratio": 3.0,
        "gain_to_pain_ratio": 2.5,
        "irr_annualized": 12.0,
        "irr_daily": 0.03,
        "avg_daily_return": 0.04,
        "max_consecutive_wins": 5,
        "max_consecutive_losses": 2,
        "num_days": 365,
        "net_pnl": 1550.0,
        "starting_balance_result": 10000.0,
        "ending_balance": 11550.0,
        "status": "ok",
        "error_msg": None,
        "elapsed_seconds": 3.5,
        "completed_at": "2026-02-28T14:30:00Z",
    }


def test_write_and_read_single_chunk():
    """Write 3 rows, flush, read back via DuckDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ParquetChunkWriter(
            output_dir=tmpdir,
            worker_id=0,
            chunk_size=3,
            experiment_config={"experiment_id": "test_exp", "name": "test"},
        )
        for i in range(3):
            writer.add_row(_make_test_row(i))
        writer.flush()
        writer.close()

        files = [f for f in os.listdir(tmpdir) if f.endswith(".parquet")]
        assert len(files) == 1
        assert files[0] == "worker_00_chunk_000.parquet"

        conn = duckdb.connect()
        df = conn.execute(
            f"SELECT * FROM read_parquet('{tmpdir}/*.parquet')"
        ).fetchdf()
        assert len(df) == 3
        assert list(df["run_index"]) == [0, 1, 2]
        assert df["experiment_id"].iloc[0] == "test_exp"
        assert df["asset"].iloc[0] == "BTC"
        conn.close()


def test_auto_flush_at_chunk_size():
    """Writer auto-flushes when buffer reaches chunk_size."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ParquetChunkWriter(
            output_dir=tmpdir, worker_id=1, chunk_size=2,
        )
        writer.add_row(_make_test_row(0))
        assert writer.buffered_rows == 1

        writer.add_row(_make_test_row(1))
        # Should have auto-flushed
        assert writer.buffered_rows == 0

        files = [f for f in os.listdir(tmpdir) if f.endswith(".parquet")]
        assert len(files) == 1
        assert files[0] == "worker_01_chunk_000.parquet"
        writer.close()


def test_multiple_chunks():
    """Writing more rows than chunk_size produces multiple files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ParquetChunkWriter(
            output_dir=tmpdir, worker_id=0, chunk_size=2,
        )
        for i in range(5):
            writer.add_row(_make_test_row(i))
        writer.close()

        files = sorted(f for f in os.listdir(tmpdir) if f.endswith(".parquet"))
        assert len(files) == 3  # 2 + 2 + 1
        assert files[0] == "worker_00_chunk_000.parquet"
        assert files[1] == "worker_00_chunk_001.parquet"
        assert files[2] == "worker_00_chunk_002.parquet"

        conn = duckdb.connect()
        df = conn.execute(
            f"SELECT * FROM read_parquet('{tmpdir}/*.parquet') ORDER BY run_index"
        ).fetchdf()
        assert len(df) == 5
        assert list(df["run_index"]) == [0, 1, 2, 3, 4]
        conn.close()


def test_experiment_config_in_metadata():
    """Experiment config is embedded in Parquet file metadata."""
    import pyarrow.parquet as pq

    with tempfile.TemporaryDirectory() as tmpdir:
        config = {"experiment_id": "meta_test", "name": "metadata test"}
        writer = ParquetChunkWriter(
            output_dir=tmpdir, worker_id=0, chunk_size=10,
            experiment_config=config,
        )
        writer.add_row(_make_test_row(0))
        writer.close()

        path = os.path.join(tmpdir, "worker_00_chunk_000.parquet")
        meta = pq.read_metadata(path)
        schema_meta = meta.schema.to_arrow_schema().metadata
        stored_config = json.loads(schema_meta[b"experiment_config"])
        assert stored_config["experiment_id"] == "meta_test"


def test_schema_has_68_columns():
    """Verify the schema has exactly 68 columns (67 + config_hash)."""
    assert len(RESULT_SCHEMA) == 68
