"""Parquet chunk writer for experiment results.

Writes backtest result rows in fixed-size chunks using PyArrow. Each chunk
file is immutable once written. Experiment config is embedded in Parquet
file metadata for provenance.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

# Full 67-column schema matching the specification.
# Grouped: identity, provenance, strategy, entry/exit signals,
# execution config, results, metadata.
RESULT_SCHEMA = pa.schema([
    # Identity
    ("experiment_id", pa.string()),
    ("run_index", pa.int32()),
    ("config_hash", pa.string()),
    # Provenance
    ("code_version", pa.string()),
    ("rng_seed", pa.int32()),
    ("data_file_path", pa.string()),
    ("data_file_hash", pa.string()),
    ("data_file_rows", pa.int32()),
    # Strategy identity
    ("strategy_name", pa.string()),
    ("asset", pa.string()),
    ("timeframe", pa.string()),
    ("start_date", pa.string()),
    ("end_date", pa.string()),
    # Entry signals (variable schema, stored as JSON)
    ("entry_json", pa.string()),
    ("trigger_name", pa.string()),
    ("num_entry_signals", pa.int16()),
    # Exit signals (variable schema, stored as JSON)
    ("exit_json", pa.string()),
    ("num_exit_signals", pa.int16()),
    # Execution config (fixed schema, flat columns)
    ("reward_factor", pa.float32()),
    ("max_risk_per_trade", pa.float32()),
    ("stop_loss_calculation", pa.string()),
    ("atr_period", pa.int16()),
    ("atr_volatility_factor", pa.float32()),
    ("atr_short_weight", pa.float32()),
    ("atr_long_weight", pa.float32()),
    ("initial_balance", pa.float32()),
    ("min_balance_threshold", pa.float32()),
    ("min_trade_amount", pa.float32()),
    ("max_open_positions", pa.int16()),
    ("max_trades_per_day", pa.int16()),
    ("max_units_per_trade", pa.float32()),
    ("max_trade_amount", pa.float32()),
    ("volatility_window", pa.int16()),
    ("target_volatility", pa.float32()),
    ("volatility_mode", pa.string()),
    ("enable_volatility_adj", pa.bool_()),
    ("max_hold_time_hours", pa.int16()),
    ("cooldown_bars", pa.int16()),
    ("daily_momentum_limit", pa.float32()),
    ("weekly_momentum_limit", pa.float32()),
    ("max_hold_bars", pa.int16()),
    ("exit_on_loss_after_bars", pa.int16()),
    ("exit_on_profit_after_bars", pa.int16()),
    ("profit_threshold_pct", pa.float32()),
    ("slippage_pct", pa.float32()),
    ("fee_pct", pa.float32()),
    # Backtest results (fixed schema, flat columns)
    ("total_trades", pa.int32()),
    ("win_rate", pa.float32()),
    ("total_return", pa.float32()),
    ("sharpe_ratio", pa.float64()),
    ("sortino_ratio", pa.float64()),
    ("max_drawdown", pa.float64()),
    ("max_drawdown_duration", pa.int32()),
    ("calmar_ratio", pa.float64()),
    ("gain_to_pain_ratio", pa.float64()),
    ("irr_annualized", pa.float64()),
    ("irr_daily", pa.float64()),
    ("avg_daily_return", pa.float64()),
    ("max_consecutive_wins", pa.int16()),
    ("max_consecutive_losses", pa.int16()),
    ("num_days", pa.int32()),
    ("net_pnl", pa.float64()),
    ("starting_balance_result", pa.float64()),
    ("ending_balance", pa.float64()),
    # Run metadata
    ("status", pa.string()),
    ("error_msg", pa.string()),
    ("elapsed_seconds", pa.float32()),
    ("completed_at", pa.string()),
])


class ParquetChunkWriter:
    """Writes result rows to Parquet files in fixed-size chunks.

    Each call to add_row() buffers one row. When the buffer reaches
    chunk_size, it flushes to a new Parquet file named
    worker_{nn}_chunk_{nnn}.parquet.

    Args:
        output_dir: Directory to write chunk files into.
        worker_id: Numeric worker ID (used in filename).
        chunk_size: Rows per chunk file (default 1024).
        experiment_config: Dict embedded in Parquet file metadata.
    """

    def __init__(
        self,
        output_dir: str,
        worker_id: int,
        chunk_size: int = 1024,
        experiment_config: dict[str, Any] | None = None,
    ):
        self.output_dir = output_dir
        self.worker_id = worker_id
        self.chunk_size = chunk_size
        self.experiment_config = experiment_config or {}
        self._buffer: list[dict[str, Any]] = []
        self._chunk_index = 0
        os.makedirs(output_dir, exist_ok=True)

    def add_row(self, row: dict[str, Any]) -> None:
        """Buffer a result row. Flushes automatically at chunk_size."""
        self._buffer.append(row)
        if len(self._buffer) >= self.chunk_size:
            self.flush()

    def flush(self) -> str | None:
        """Write buffered rows to a Parquet chunk file.

        Returns the file path written, or None if buffer was empty.
        """
        if not self._buffer:
            return None

        filename = f"worker_{self.worker_id:02d}_chunk_{self._chunk_index:03d}.parquet"
        path = os.path.join(self.output_dir, filename)

        # Build columnar arrays from row dicts
        columns = {}
        for field in RESULT_SCHEMA:
            col_name = field.name
            values = [row.get(col_name) for row in self._buffer]
            columns[col_name] = values

        table = pa.table(columns, schema=RESULT_SCHEMA)

        # Embed experiment config in file metadata
        metadata = table.schema.metadata or {}
        metadata[b"experiment_config"] = json.dumps(
            self.experiment_config
        ).encode("utf-8")
        table = table.replace_schema_metadata(metadata)

        pq.write_table(table, path, compression="snappy")

        self._chunk_index += 1
        self._buffer.clear()
        return path

    def close(self) -> None:
        """Flush any remaining rows."""
        self.flush()

    @property
    def rows_written(self) -> int:
        """Total rows written across all chunks (not including buffer)."""
        return self._chunk_index * self.chunk_size

    @property
    def buffered_rows(self) -> int:
        """Rows currently in the buffer (not yet flushed)."""
        return len(self._buffer)
