"""DuckDB query service for Parquet experiment results.

Provides filtered, sorted, paginated queries over Parquet files using
DuckDB's in-process SQL engine. Also supports counting completed
run_indices for experiment resume.
"""

from __future__ import annotations

import os
from typing import Any

import duckdb


# Columns that are safe to filter/sort on (prevent SQL injection)
_ALLOWED_FILTER_COLUMNS = {
    "asset", "timeframe", "trigger_name", "status",
    "reward_factor", "max_risk_per_trade", "max_open_positions",
    "cooldown_bars", "target_volatility", "atr_period",
    "atr_volatility_factor", "max_hold_bars", "volatility_window",
    "max_trades_per_day", "enable_volatility_adj",
    "slippage_pct", "fee_pct",
    "stop_loss_calculation", "volatility_mode",
}

_ALLOWED_SORT_COLUMNS = {
    "sharpe_ratio", "sortino_ratio", "total_return", "max_drawdown",
    "calmar_ratio", "gain_to_pain_ratio", "win_rate", "total_trades",
    "net_pnl", "ending_balance", "irr_annualized", "elapsed_seconds",
    "run_index", "num_entry_signals", "reward_factor", "cooldown_bars",
    "atr_period", "max_risk_per_trade",
}


def _parquet_glob(experiment_dir: str) -> str:
    """Build the glob pattern for an experiment's Parquet files."""
    return os.path.join(experiment_dir, "results", "**", "*.parquet")


def query_results(
    experiment_dir: str,
    filters: dict[str, Any] | None = None,
    sort: str = "sharpe_ratio",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
    min_trades: int = 0,
    min_sharpe: float | None = None,
    min_win_rate: float | None = None,
) -> dict[str, Any]:
    """Query experiment results with filters, sort, and pagination.

    Args:
        experiment_dir: Path to the experiment directory containing results/.
        filters: Dict of {column_name: value} to filter on.
        sort: Column name to sort by.
        order: "asc" or "desc".
        limit: Maximum rows to return.
        offset: Pagination offset.
        min_trades: Minimum total_trades threshold.
        min_sharpe: Minimum sharpe_ratio threshold.
        min_win_rate: Minimum win_rate threshold.

    Returns:
        Dict with "total", "offset", "limit", and "results" (list of dicts).
    """
    glob = _parquet_glob(experiment_dir)

    if not _has_parquet_files(experiment_dir):
        return {"total": 0, "offset": offset, "limit": limit, "results": []}

    where_parts = []
    params = []

    if filters:
        for col, val in filters.items():
            if col not in _ALLOWED_FILTER_COLUMNS:
                continue
            where_parts.append(f'"{col}" = ?')
            params.append(val)

    if min_trades > 0:
        where_parts.append("total_trades >= ?")
        params.append(min_trades)

    if min_sharpe is not None:
        where_parts.append("sharpe_ratio >= ?")
        params.append(min_sharpe)

    if min_win_rate is not None:
        where_parts.append("win_rate >= ?")
        params.append(min_win_rate)

    where_sql = " AND ".join(where_parts) if where_parts else "1=1"

    # Validate sort column
    if sort not in _ALLOWED_SORT_COLUMNS:
        sort = "sharpe_ratio"
    order_sql = "DESC" if order.lower() == "desc" else "ASC"

    conn = duckdb.connect()

    # Count query
    count_sql = f"""
        SELECT COUNT(*) as cnt FROM read_parquet('{glob}')
        WHERE {where_sql}
    """
    total = conn.execute(count_sql, params).fetchone()[0]

    # Data query
    data_sql = f"""
        SELECT * FROM read_parquet('{glob}')
        WHERE {where_sql}
        ORDER BY "{sort}" {order_sql} NULLS LAST
        LIMIT ? OFFSET ?
    """
    data_params = params + [limit, offset]
    df = conn.execute(data_sql, data_params).fetchdf()

    conn.close()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": df.to_dict("records"),
    }


def count_completed(experiment_dir: str) -> set[int]:
    """Return the set of completed run_index values from Parquet files.

    Used for experiment resume -- workers skip run_indices in this set.
    """
    glob = _parquet_glob(experiment_dir)

    if not _has_parquet_files(experiment_dir):
        return set()

    conn = duckdb.connect()
    result = conn.execute(
        f"SELECT run_index FROM read_parquet('{glob}')"
    ).fetchnumpy()
    conn.close()

    return set(int(x) for x in result["run_index"])


def get_result_row(experiment_dir: str, run_index: int) -> dict[str, Any] | None:
    """Fetch a single result row by run_index.

    Used for backtest visualization -- reconstructs the strategy config
    from the stored columns.
    """
    glob = _parquet_glob(experiment_dir)

    if not _has_parquet_files(experiment_dir):
        return None

    conn = duckdb.connect()
    df = conn.execute(
        f"SELECT * FROM read_parquet('{glob}') WHERE run_index = ?",
        [run_index],
    ).fetchdf()
    conn.close()

    if df.empty:
        return None

    return df.iloc[0].to_dict()


def _has_parquet_files(experiment_dir: str) -> bool:
    """Check if there are any Parquet files in the results directory."""
    results_dir = os.path.join(experiment_dir, "results")
    if not os.path.isdir(results_dir):
        return False
    for root, _, files in os.walk(results_dir):
        for f in files:
            if f.endswith(".parquet"):
                return True
    return False
