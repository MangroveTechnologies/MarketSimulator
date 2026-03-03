"""Generate daily companion OHLCV files from sub-daily CSVs.

For each sub-daily CSV in data/ohlcv/ (1h, 4h, 5m, 15m, 30m), resamples
to daily OHLCV and saves alongside the original. The backtest engine needs
both the signal timeframe AND daily data for ATR calculations.

Crypto trades 24/7, so resampling to daily is lossless -- a daily candle IS
the aggregation of all sub-daily bars within that UTC calendar day.

Usage:
    python scripts/generate_daily_companions.py [ohlcv_dir]

Default directory: data/ohlcv/
"""

import os
import re
import sys

import pandas as pd

FILENAME_RE = re.compile(
    r"^([a-z][a-z0-9]*)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})_(\w+)\.csv$"
)

DAILY_TIMEFRAMES = {"1d", "1D"}


def companion_daily_filename(data_file: str) -> str:
    """Derive the daily companion filename from a sub-daily OHLCV filename."""
    base, ext = os.path.splitext(data_file)
    prefix = base.rsplit("_", 1)[0]
    return f"{prefix}_1d{ext}"


def resample_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Resample sub-daily OHLCV to daily bars (UTC calendar day boundaries)."""
    daily = (
        df.set_index("timestamp")
        .resample("1D")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(subset=["open"])
        .reset_index()
    )
    return daily


def main():
    ohlcv_dir = sys.argv[1] if len(sys.argv) > 1 else "data/ohlcv"

    if not os.path.isdir(ohlcv_dir):
        print(f"OHLCV directory not found: {ohlcv_dir}")
        sys.exit(1)

    generated = 0
    skipped = 0

    for fname in sorted(os.listdir(ohlcv_dir)):
        match = FILENAME_RE.match(fname)
        if not match:
            continue

        timeframe = match.group(4)
        if timeframe in DAILY_TIMEFRAMES:
            continue

        companion = companion_daily_filename(fname)
        companion_path = os.path.join(ohlcv_dir, companion)
        source_path = os.path.join(ohlcv_dir, fname)

        # Skip if companion exists and is newer than source
        if os.path.isfile(companion_path):
            if os.path.getmtime(companion_path) >= os.path.getmtime(source_path):
                skipped += 1
                continue

        df = pd.read_csv(source_path)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        df.sort_values("timestamp", inplace=True)

        daily = resample_to_daily(df)
        daily.to_csv(companion_path, index=False)
        generated += 1
        print(f"  {fname} -> {companion} ({len(daily)} daily bars)")

    print(f"Daily companions: {generated} generated, {skipped} up-to-date")


if __name__ == "__main__":
    main()
