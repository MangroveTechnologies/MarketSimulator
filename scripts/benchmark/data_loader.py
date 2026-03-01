"""
Data file discovery for copilot benchmarking.

Scans the data directory for OHLCV CSV files matching the standard naming
convention and builds the list of available (asset, timeframe) pairs.

Expected filename format::

    {asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv

Examples::

    btc_2022-08-01_2026-02-15_1d.csv
    eth_2024-01-01_2026-02-01_4h.csv
    doge_2021-04-01_2021-06-15_5m.csv

Files with exchange names, hour-level dates, or non-standard timeframe
labels (e.g., ``1HRS``, ``hourly``) are ignored.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

# Matches: {asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv
# Captures: asset, start_date, end_date, timeframe
_FILENAME_PATTERN = re.compile(
    r"^([a-z][a-z0-9]*)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_(\w+)\.csv$",
    re.IGNORECASE,
)

# Valid timeframe suffixes (lowercase)
_VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"}

# Default data directory inside the Docker container
# OHLCV source data lives in MangroveAI (runtime dependency)
DEFAULT_DATA_DIR = "/app/MangroveAI/data"


@dataclass
class DataFile:
    """A discovered OHLCV data file.

    Attributes:
        asset: Uppercase asset symbol (e.g., "BTC").
        timeframe: Timeframe string (e.g., "1d", "4h", "5m").
        start_date: Start date parsed from filename.
        end_date: End date parsed from filename.
        filename: The CSV filename.
        filepath: Full path to the file.
    """
    asset: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    filename: str
    filepath: str


def discover_data_files(data_dir: str = DEFAULT_DATA_DIR) -> List[DataFile]:
    """Scan the data directory for OHLCV files matching the standard format.

    Only files matching ``{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv``
    with a recognized timeframe are returned.

    Args:
        data_dir: Path to the data directory.

    Returns:
        List of DataFile objects sorted by (asset, timeframe).
    """
    if not os.path.isdir(data_dir):
        raise FileNotFoundError(f"Data directory not found: {data_dir}")

    files = []
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
            start_date = datetime.strptime(start_str, "%Y-%m-%d")
            end_date = datetime.strptime(end_str, "%Y-%m-%d")
        except ValueError:
            continue

        files.append(DataFile(
            asset=asset_raw.upper(),
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            filename=filename,
            filepath=os.path.join(data_dir, filename),
        ))

    files.sort(key=lambda f: (f.asset, f.timeframe))
    return files


def get_asset_timeframes(data_dir: str = DEFAULT_DATA_DIR) -> List[tuple]:
    """Return a list of (asset, timeframe) tuples from available data files.

    This is the primary interface for the scenario generator.

    Args:
        data_dir: Path to the data directory.

    Returns:
        List of (asset, timeframe) tuples, e.g., [("BTC", "1d"), ("ETH", "4h")].
    """
    files = discover_data_files(data_dir)
    return [(f.asset, f.timeframe) for f in files]


def get_data_file_map(data_dir: str = DEFAULT_DATA_DIR) -> Dict[str, DataFile]:
    """Return a dict mapping ``"ASSET_timeframe"`` to DataFile objects.

    Useful for looking up the file path and date range for a given combo.

    Args:
        data_dir: Path to the data directory.

    Returns:
        Dict keyed by ``"{ASSET}_{timeframe}"`` (e.g., ``"BTC_1d"``).
    """
    files = discover_data_files(data_dir)
    return {f"{f.asset}_{f.timeframe}": f for f in files}
