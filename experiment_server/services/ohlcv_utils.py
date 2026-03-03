"""Shared OHLCV cache utilities for sweep workers and visualization.

Both the sweep worker and visualize service need to inject local CSV data
into MangroveAI's _OHLCV_CACHE so the backtest engine reads from files
instead of calling CoinAPI.

The engine needs TWO timeframes for any sub-daily strategy:
  1. The signal timeframe (e.g., 1h) for signal evaluation
  2. Daily (1D) for ATR baseline calculation

Cache keys must match EXACTLY what the engine constructs in
MarketDataLoader.load() -- a 5-tuple of (provider, asset, interval,
start_iso, end_iso) where dates are adjusted for ATR pre-history.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import pandas as pd


def compute_cache_keys(
    asset: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    atr_period: int = 14,
) -> dict[str, tuple]:
    """Compute _OHLCV_CACHE keys matching the engine's lookup pattern.

    The engine (via fetch_strategy_market_data in market_data.py) adjusts
    date ranges before creating MarketDataLoader instances:
      - fetch_start = start_date - atr_period days     (line 173)
      - signal TF start = fetch_start                   (line 208)
      - daily TF start = fetch_start - atr_period days  (line 206)
      - end = end_date (unchanged)

    MarketDataLoader.load() then builds the cache key from:
      (provider.lower(), asset.upper(), interval.lower(),
       start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ"))

    Args:
        asset: Raw asset name (e.g., "paxg"). Will be uppercased with "-USDT" appended.
        timeframe: Signal timeframe (e.g., "1h", "4h", "5m").
        start_date: Backtest start date (as passed to BacktestRequest).
        end_date: Backtest end date.
        atr_period: ATR period from execution config.

    Returns:
        Dict mapping timeframe label to cache key tuple.
        Always has the signal timeframe; has "1d" if signal TF is sub-daily.
    """
    asset_pair = f"{asset.upper()}-USDT"
    fetch_start = start_date - timedelta(days=atr_period)
    end_iso = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")

    keys: dict[str, tuple] = {}

    # Signal timeframe
    signal_start = fetch_start
    keys[timeframe.lower()] = (
        "coinapi",
        asset_pair,
        timeframe.lower(),
        signal_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_iso,
    )

    # Daily companion (only if signal TF is sub-daily)
    if timeframe.lower() != "1d":
        daily_start = fetch_start - timedelta(days=atr_period)
        keys["1d"] = (
            "coinapi",
            asset_pair,
            "1d",
            daily_start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end_iso,
        )

    return keys


def companion_daily_filename(data_file: str) -> str:
    """Derive the daily companion filename from a sub-daily OHLCV filename.

    Example: "paxg_2025-01-01_2026-02-14_1h.csv" -> "paxg_2025-01-01_2026-02-14_1d.csv"
    """
    base, ext = os.path.splitext(data_file)
    prefix = base.rsplit("_", 1)[0]
    return f"{prefix}_1d{ext}"


def load_ohlcv_csv(csv_path: str) -> pd.DataFrame:
    """Load an OHLCV CSV file into a standardized DataFrame."""
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def inject_ohlcv_for_run(
    ds_module: Any,
    ohlcv_dir: str,
    data_file: str,
    asset: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    atr_period: int = 14,
    df_primary: pd.DataFrame | None = None,
    df_daily: pd.DataFrame | None = None,
) -> list[tuple]:
    """Inject OHLCV data into _OHLCV_CACHE for both signal TF and daily.

    Args:
        ds_module: The MangroveAI data_source module (has _OHLCV_CACHE dict).
        ohlcv_dir: Directory containing OHLCV CSV files.
        data_file: Primary OHLCV filename (e.g., "paxg_2025-01-01_2026-02-14_1h.csv").
        asset: Raw asset name (e.g., "paxg").
        timeframe: Signal timeframe (e.g., "1h").
        start_date: Backtest start date.
        end_date: Backtest end date.
        atr_period: ATR period from execution config.
        df_primary: Pre-loaded primary DataFrame (avoids re-reading CSV).
        df_daily: Pre-loaded daily DataFrame (avoids re-reading CSV).

    Returns:
        List of cache keys that were injected (for cleanup).
    """
    keys = compute_cache_keys(asset, timeframe, start_date, end_date, atr_period)

    # Load and inject primary timeframe
    if df_primary is None:
        df_primary = load_ohlcv_csv(os.path.join(ohlcv_dir, data_file))
    ds_module._OHLCV_CACHE[keys[timeframe.lower()]] = df_primary

    # Load and inject daily companion (if sub-daily)
    if "1d" in keys:
        if df_daily is None:
            companion = companion_daily_filename(data_file)
            companion_path = os.path.join(ohlcv_dir, companion)
            if not os.path.isfile(companion_path):
                raise FileNotFoundError(
                    f"Daily companion not found: {companion_path}. "
                    f"Run: python scripts/generate_daily_companions.py {ohlcv_dir}"
                )
            df_daily = load_ohlcv_csv(companion_path)
        ds_module._OHLCV_CACHE[keys["1d"]] = df_daily

    return list(keys.values())


def cleanup_ohlcv_cache(ds_module: Any, cache_keys: list[tuple]) -> None:
    """Remove injected entries from _OHLCV_CACHE."""
    for key in cache_keys:
        ds_module._OHLCV_CACHE.pop(key, None)
