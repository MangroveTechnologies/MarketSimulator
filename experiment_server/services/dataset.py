"""Dataset discovery and file hashing service.

Scans a data directory for OHLCV CSV files matching the naming convention:
    {asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv

Returns DatasetSelection models with asset, timeframe, date range, row count,
file path, and SHA256 hash.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime

from experiment_server.models.experiment import DatasetSelection

# Matches: {asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv
_FILENAME_PATTERN = re.compile(
    r"^([a-z][a-z0-9]*)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_(\w+)\.csv$",
    re.IGNORECASE,
)

_VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}


def compute_file_hash(path: str) -> str:
    """Compute SHA256 hash of a file. Returns 'sha256:{hex}'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _count_data_rows(path: str) -> int:
    """Count data rows in a CSV (total lines minus header)."""
    with open(path) as f:
        return max(0, sum(1 for _ in f) - 1)


def discover_datasets(data_dir: str) -> list[DatasetSelection]:
    """Scan a directory for OHLCV CSV files matching the naming convention.

    Args:
        data_dir: Path to scan for CSV files.

    Returns:
        Sorted list of DatasetSelection models.
    """
    if not os.path.isdir(data_dir):
        return []

    results = []
    for filename in os.listdir(data_dir):
        if not filename.endswith(".csv"):
            continue

        match = _FILENAME_PATTERN.match(filename)
        if not match:
            continue

        asset_raw, start_str, end_str, tf_raw = match.groups()
        timeframe = tf_raw.lower()

        if timeframe not in _VALID_TIMEFRAMES:
            continue

        try:
            datetime.strptime(start_str, "%Y-%m-%d")
            datetime.strptime(end_str, "%Y-%m-%d")
        except ValueError:
            continue

        filepath = os.path.join(data_dir, filename)
        rows = _count_data_rows(filepath)

        results.append(DatasetSelection(
            asset=asset_raw.upper(),
            timeframe=timeframe,
            file=filename,
            rows=rows,
            start_date=start_str,
            end_date=end_str,
        ))

    results.sort(key=lambda d: (d.asset, d.timeframe))
    return results
