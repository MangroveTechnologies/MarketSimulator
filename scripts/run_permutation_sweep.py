"""
Backtesting signal permutation sweep.

For each symbol x trigger x trigger_params x filter x filter_params, runs a
full backtest via the service layer and appends one row of metrics to a CSV.

Lives in MarketSimulator but depends on MangroveAI's backtest engine at runtime.
Run inside a container with both projects mounted:
  docker exec -w /app/MarketSimulator/scripts mangrove-sweep python run_permutation_sweep.py [options]

All data is loaded from local CSV files -- no CoinAPI calls.

Signal source (--signals):
  hardcoded  Use the curated TRIGGER_SIGNALS / FILTER_SIGNALS lists defined in this file (default).
  kb         Load all numeric-param signals from signals_metadata.json (same file the app uses).
             Signals with str/bool params (direction, username, etc.) are skipped automatically.

Usage examples:
  # Hardcoded signals, 3 total param combos per signal:
  python run_permutation_sweep.py --n-trigger 3 --n-filter 3

  # All KB signals:
  python run_permutation_sweep.py --signals kb --n-trigger 3 --n-filter 3

  # KB signals, restrict to specific names:
  python run_permutation_sweep.py --signals kb --trigger-signals ema_cross_up,macd_bullish_cross --filter-signals rsi_oversold

  # Resume a previous run (reads last row of CSV and skips to next combo):
  python run_permutation_sweep.py --n-trigger 3 --n-filter 3 --resume

  # Custom output path:
  python run_permutation_sweep.py --output /app/MarketSimulator/data/sweep_results.csv

  # Dry-run: print the combo plan without running backtests:
  python run_permutation_sweep.py --n-trigger 3 --n-filter 3 --dry-run
"""

import argparse
import csv
import json
import os
import sys
import time
import traceback
from datetime import datetime
from itertools import product
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, "/app")

# Suppress noisy backtest engine loggers -- remove once logging upgrade (Phase 1) is complete
import logging as _logging
for _noisy in [
    "MangroveAI.domains.backtesting",
    "MangroveAI.domains.strategies",
    "MangroveAI.domains.managers",
    "MangroveAI.domains.positions",
]:
    _logging.getLogger(_noisy).setLevel(_logging.WARNING)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = "/app/MangroveAI/data"
SIGNALS_METADATA_PATH = "/app/MangroveAI/domains/signals/signals_metadata.json"

# ---------------------------------------------------------------------------
# Symbol registry
# interval: the timeframe string used by the backtest engine and cache key
# ---------------------------------------------------------------------------

SYMBOLS = {
    "BTC": {
        "file": "btc_2022-08-01_2026-02-15_1d.csv",
        "asset": "BTC-USDT",
        "interval": "1d",
        "start": datetime(2022, 8, 1),
        "end": datetime(2026, 2, 15),
    },
    "ETH": {
        "file": "eth_2024-01-01_2026-02-01_4h.csv",
        "asset": "ETH-USDT",
        "interval": "4h",
        "start": datetime(2024, 1, 1),
        "end": datetime(2026, 2, 1),
    },
    "LINK": {
        "file": "link_2025-07-04_2026-02-12_30m.csv",
        "asset": "LINK-USDT",
        "interval": "30m",
        "start": datetime(2025, 7, 4),
        "end": datetime(2026, 2, 12),
    },
    "PAXG": {
        "file": "paxg_2025-01-01_2026-02-14_1h.csv",
        "asset": "PAXG-USDT",
        "interval": "1h",
        "start": datetime(2025, 1, 1),
        "end": datetime(2026, 2, 14),
    },
    "DOGE": {
        "file": "doge_2021-04-01_2021-06-15_5m.csv",
        "asset": "DOGE-USDT",
        "interval": "5m",
        "start": datetime(2021, 4, 1),
        "end": datetime(2021, 6, 15),
    },
    "SOL": {
        "file": "sol_2026-02-01_2026-02-16_5m.csv",
        "asset": "SOL-USDT",
        "interval": "5m",
        "start": datetime(2026, 2, 1),
        "end": datetime(2026, 2, 16),
    },
}

# ---------------------------------------------------------------------------
# Signal definitions
# Each entry: signal_name, signal_type, timeframe, param_grid
# param_grid is a list of param dicts (each dict = one combo to test).
# The grid is built at runtime by build_param_grid() based on --n-trigger/--n-filter.
# ---------------------------------------------------------------------------

# Trigger signals (TRIGGER type - fires on state change)
TRIGGER_SIGNALS = [
    {
        "name": "ema_cross_up",
        "signal_type": "TRIGGER",
        "timeframe": "1h",
        "param_ranges": {
            "window_fast": {"min": 5,  "max": 30,  "default": 9},
            "window_slow": {"min": 20, "max": 100, "default": 21},
        },
        "constraints": [("window_fast", "<", "window_slow")],
    },
    {
        "name": "macd_bullish_cross",
        "signal_type": "TRIGGER",
        "timeframe": "1h",
        "param_ranges": {
            "window_fast": {"min": 8,  "max": 20,  "default": 12},
            "window_slow": {"min": 20, "max": 35,  "default": 26},
            "window_sign": {"min": 5,  "max": 15,  "default": 9},
        },
        "constraints": [("window_fast", "<", "window_slow")],
    },
    {
        "name": "rsi_cross_up",
        "signal_type": "TRIGGER",
        "timeframe": "1h",
        "param_ranges": {
            "window":    {"min": 7,  "max": 28,  "default": 14},
            "threshold": {"min": 40, "max": 60,  "default": 50},
        },
        "constraints": [],
    },
    {
        "name": "sma_cross_up",
        "signal_type": "TRIGGER",
        "timeframe": "1h",
        "param_ranges": {
            "window_fast": {"min": 5,  "max": 30,  "default": 10},
            "window_slow": {"min": 20, "max": 100, "default": 50},
        },
        "constraints": [("window_fast", "<", "window_slow")],
    },
    {
        "name": "stochrsi_oversold",
        "signal_type": "TRIGGER",
        "timeframe": "1h",
        "param_ranges": {
            "window":    {"min": 7,  "max": 21,  "default": 14},
            "smooth1":   {"min": 2,  "max": 5,   "default": 3},
            "smooth2":   {"min": 2,  "max": 5,   "default": 3},
            "threshold": {"min": 0.1, "max": 0.3, "default": 0.2},
        },
        "constraints": [],
    },
]

# Filter signals (FILTER type - state-based, true while condition holds)
FILTER_SIGNALS = [
    {
        "name": "cmf_bullish",
        "signal_type": "FILTER",
        "timeframe": "1h",
        "param_ranges": {
            "window":    {"min": 10, "max": 30,   "default": 20},
            "threshold": {"min": 0.0, "max": 0.1, "default": 0.0},
        },
        "constraints": [],
    },
    {
        "name": "rsi_oversold",
        "signal_type": "FILTER",
        "timeframe": "1h",
        "param_ranges": {
            "window":    {"min": 7,  "max": 28,  "default": 14},
            "threshold": {"min": 25, "max": 40,  "default": 30},
        },
        "constraints": [],
    },
    {
        "name": "vwap_above",
        "signal_type": "FILTER",
        "timeframe": "1h",
        "param_ranges": {
            "window": {"min": 5, "max": 30, "default": 14},
        },
        "constraints": [],
    },
    {
        "name": "adx_strong_trend",
        "signal_type": "FILTER",
        "timeframe": "1h",
        "param_ranges": {
            "window":    {"min": 7,  "max": 28,  "default": 14},
            "threshold": {"min": 20, "max": 35,  "default": 25},
        },
        "constraints": [],
    },
    {
        "name": "obv_bullish",
        "signal_type": "FILTER",
        "timeframe": "1h",
        "param_ranges": {
            "window": {"min": 10, "max": 40, "default": 20},
        },
        "constraints": [],
    },
]

# ---------------------------------------------------------------------------
# KB signal loader -- reads signals_metadata.json, returns signal defs in the
# same shape as TRIGGER_SIGNALS / FILTER_SIGNALS.
# Signals with non-numeric params (str, bool) or missing min/max are skipped.
# ---------------------------------------------------------------------------

_NUMERIC_TYPES = {"int", "float", "integer", None}
_DEFAULT_TIMEFRAME = "1h"


def _is_sweepable_param(spec: Dict) -> bool:
    return (
        spec.get("type") in _NUMERIC_TYPES
        and "min" in spec
        and "max" in spec
    )


def load_signals_from_metadata(
    sig_type: str,
    name_filter: Optional[List[str]] = None,
) -> List[Dict]:
    """
    Load all sweepable signals of the given type ('TRIGGER' or 'FILTER') from
    signals_metadata.json.  A signal is sweepable when all its params have
    numeric type and explicit min/max bounds.  Signals with str/bool/missing
    params are silently skipped.

    Args:
        sig_type:    'TRIGGER' or 'FILTER'
        name_filter: if provided, only return signals whose name is in this list.

    Returns:
        List of signal defs in the same format as TRIGGER_SIGNALS / FILTER_SIGNALS.
    """
    with open(SIGNALS_METADATA_PATH) as f:
        metadata = json.load(f)

    skipped = []
    results = []
    for name, meta in metadata.items():
        if meta.get("type") != sig_type:
            continue
        if name_filter and name not in name_filter:
            continue

        params = meta.get("params", {})
        if not params:
            skipped.append((name, "no params"))
            continue

        non_sweepable = [p for p, spec in params.items() if not _is_sweepable_param(spec)]
        if non_sweepable:
            skipped.append((name, f"non-numeric params: {non_sweepable}"))
            continue

        param_ranges = {}
        for pname, spec in params.items():
            entry = {"min": spec["min"], "max": spec["max"]}
            if "default" in spec:
                entry["default"] = spec["default"]
            if spec.get("type") in ("int", "integer") or (
                isinstance(spec["min"], int) and isinstance(spec["max"], int)
            ):
                entry["type"] = "int"
            else:
                entry["type"] = "float"
            param_ranges[pname] = entry

        # Infer constraints: any pair where name contains fast/slow implies fast < slow
        constraints = []
        pnames = list(param_ranges.keys())
        if "window_fast" in pnames and "window_slow" in pnames:
            constraints.append(("window_fast", "<", "window_slow"))

        results.append({
            "name": name,
            "signal_type": sig_type,
            "timeframe": _DEFAULT_TIMEFRAME,
            "param_ranges": param_ranges,
            "constraints": constraints,
        })

    if skipped:
        print(f"[KB] Skipped {len(skipped)} {sig_type} signals (non-numeric/no-range params):")
        for name, reason in skipped:
            print(f"     {name}: {reason}")

    results.sort(key=lambda s: s["name"])
    return results


# ---------------------------------------------------------------------------
# Execution config applied to every backtest
# ---------------------------------------------------------------------------
EXECUTION_CONFIG = {
    "max_risk_per_trade": 0.01,
    "reward_factor": 2.0,
    "stop_loss_calculation": "dynamic_atr",
    "atr_period": 14,
    "atr_volatility_factor": 2.0,
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
}

# ---------------------------------------------------------------------------
# CSV output columns
# ---------------------------------------------------------------------------
OUTPUT_COLUMNS = [
    "run_id",
    "symbol",
    "trigger_name",
    "trigger_params",
    "filter_name",
    "filter_params",
    "timeframe",
    "start_date",
    "end_date",
    "total_trades",
    "win_rate",
    "annual_return",
    "sharpe_ratio",
    "sortino_ratio",
    "max_drawdown",
    "calmar_ratio",
    "net_pnl",
    "starting_balance",
    "ending_balance",
    "status",   # "ok" | "error" | "no_trades"
    "error_msg",
    "elapsed_seconds",
    "timestamp",
]

DEFAULT_OUTPUT = "/app/MarketSimulator/data/permutation_sweep_results.csv"


# ---------------------------------------------------------------------------
# Param grid builder
# ---------------------------------------------------------------------------

# Resolution used to build the full candidate pool per parameter before
# sampling down to n total combos. Large enough to give good coverage.
_POOL_RESOLUTION = 20


def _candidates_for_param(spec: Dict) -> List:
    """
    Generate the full candidate list for a single parameter using _POOL_RESOLUTION
    evenly-spaced values across [min, max], always including the default.
    Returns ints for int params, floats for float params.
    """
    lo, hi = spec["min"], spec["max"]
    default = spec.get("default")
    is_int = spec.get("type", "float") == "int" or (
        isinstance(lo, int) and isinstance(hi, int) and
        (default is None or isinstance(default, int))
    )

    raw = np.linspace(lo, hi, _POOL_RESOLUTION)
    if is_int:
        vals = sorted(set(int(round(v)) for v in raw))
        if default is not None and int(default) not in vals:
            vals = sorted(set(vals) | {int(default)})
    else:
        vals = sorted(set(round(float(v), 4) for v in raw))
        if default is not None:
            d = round(float(default), 4)
            if d not in vals:
                vals = sorted(set(vals) | {d})

    return vals


def _passes_constraints(d: Dict, constraints: List[Tuple]) -> bool:
    for (a, op, b) in constraints:
        if op == "<" and not (d[a] < d[b]):
            return False
        if op == "<=" and not (d[a] <= d[b]):
            return False
        if op == ">" and not (d[a] > d[b]):
            return False
    return True


_MAX_POOL_SIZE = 50_000


def _build_default_combo(ranges: Dict, constraints: List[Tuple]) -> Optional[Dict]:
    """Return the all-defaults combo if every param has a default and it passes constraints."""
    if not all("default" in spec for spec in ranges.values()):
        return None
    dc = {}
    for pname, spec in ranges.items():
        is_int = spec.get("type") == "int" or (
            isinstance(spec["min"], int) and isinstance(spec["max"], int)
        )
        dc[pname] = int(spec["default"]) if is_int else round(float(spec["default"]), 4)
    return dc if _passes_constraints(dc, constraints) else None


def build_param_grid(signal_def: Dict, n: int) -> List[Dict]:
    """
    Build exactly n param combos for a signal.

    For signals where the full cartesian product fits within _MAX_POOL_SIZE:
      - Build the full constraint-filtered pool, sample n evenly-spaced combos.

    For signals where the pool would exceed _MAX_POOL_SIZE (e.g. 9-param signals):
      - Sample n independent combos by drawing one value per parameter
        from its candidate list at evenly-spaced indices, avoiding the
        full cartesian product.

    In both cases the all-defaults combo is always included if it exists and
    passes constraints.

    n is the *total* number of combos returned regardless of parameter count.
    """
    ranges = signal_def["param_ranges"]
    constraints = signal_def.get("constraints", [])
    param_names = list(ranges.keys())

    per_param = {pname: _candidates_for_param(spec) for pname, spec in ranges.items()}
    default_combo = _build_default_combo(ranges, constraints)

    # Estimate pool size before materializing
    estimated_pool = 1
    for vals in per_param.values():
        estimated_pool *= len(vals)
        if estimated_pool > _MAX_POOL_SIZE:
            break

    if estimated_pool <= _MAX_POOL_SIZE:
        # Build full constraint-filtered pool and sample evenly
        pool = []
        for combo in product(*[per_param[p] for p in param_names]):
            d = dict(zip(param_names, combo))
            if _passes_constraints(d, constraints):
                pool.append(d)

        if not pool:
            return [default_combo] if default_combo else []

        if n >= len(pool):
            return pool

        indices = set(int(round(i)) for i in np.linspace(0, len(pool) - 1, n))
        if default_combo is not None:
            try:
                indices.add(pool.index(default_combo))
            except ValueError:
                pass
        return [pool[i] for i in sorted(indices)]

    else:
        # Pool too large: sample n combos by picking one value per param
        # at evenly-spaced positions, generating n independent combinations.
        # Constraints are applied; up to 5*n attempts are made to find valid combos.
        rng = np.random.default_rng(seed=42)
        seen = set()
        results = []

        if default_combo is not None:
            results.append(default_combo)
            seen.add(tuple(default_combo[p] for p in param_names))

        max_attempts = max(n * 10, 500)
        attempts = 0
        while len(results) < n and attempts < max_attempts:
            attempts += 1
            d = {}
            for pname in param_names:
                vals = per_param[pname]
                d[pname] = vals[int(rng.integers(0, len(vals)))]
            if not _passes_constraints(d, constraints):
                continue
            key = tuple(d[p] for p in param_names)
            if key in seen:
                continue
            seen.add(key)
            results.append(d)

        return results


# ---------------------------------------------------------------------------
# Local CSV loader - bypasses CoinAPI entirely
# ---------------------------------------------------------------------------

def load_local_csv(symbol_key: str) -> pd.DataFrame:
    meta = SYMBOLS[symbol_key]
    path = os.path.join(DATA_DIR, meta["file"])
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ---------------------------------------------------------------------------
# Backtest runner using local data
# ---------------------------------------------------------------------------

def run_single_backtest(
    symbol_key: str,
    trigger: Dict,
    trigger_params: Dict,
    filter_sig: Dict,
    filter_params: Dict,
    df_local: pd.DataFrame,
) -> Dict:
    """
    Build a strategy JSON, inject local DataFrame into the OHLCV cache,
    and run the backtest service. Returns a dict of metrics.
    """
    import io
    from MangroveAI.domains.backtesting.services import run_backtest
    from MangroveAI.domains.backtesting.domain_models.requests import BacktestRequest
    from MangroveAI.domains.backtesting import data_source as ds_module

    meta = SYMBOLS[symbol_key]
    interval = meta["interval"]

    strategy_config = {
        "name": f"sweep_{symbol_key}_{trigger['name']}_{filter_sig['name']}",
        "asset": meta["asset"].split("-")[0],
        "entry": [
            {
                "name": trigger["name"],
                "signal_type": "TRIGGER",
                "timeframe": interval,
                "params": trigger_params,
            },
            {
                "name": filter_sig["name"],
                "signal_type": "FILTER",
                "timeframe": interval,
                "params": filter_params,
            },
        ],
        "exit": [],
        "reward_factor": EXECUTION_CONFIG["reward_factor"],
        "execution_config": EXECUTION_CONFIG,
    }

    # Inject local DataFrame into the in-process OHLCV cache.
    # Cache key must match exactly what data_source.py builds.
    cache_key = (
        "coinapi",
        meta["asset"].split("-")[0].upper(),
        interval.lower(),
        meta["start"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        meta["end"].strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    ds_module._OHLCV_CACHE[cache_key] = df_local

    # Suppress print() output from the backtest engine (tick-level prints flood stdout).
    # Remove this block once logging Phase 1 (print -> logger) is complete.
    _devnull = open(os.devnull, "w")
    _old_stdout = sys.stdout
    sys.stdout = _devnull

    request = BacktestRequest(
        initial_balance=10000.0,
        min_balance_threshold=0.1,
        min_trade_amount=25.0,
        max_open_positions=int(EXECUTION_CONFIG["max_open_positions"]),
        max_trades_per_day=int(EXECUTION_CONFIG["max_trades_per_day"]),
        max_risk_per_trade=float(EXECUTION_CONFIG["max_risk_per_trade"]),
        max_units_per_trade=float(EXECUTION_CONFIG["max_units_per_trade"]),
        max_trade_amount=float(EXECUTION_CONFIG["max_trade_amount"]),
        volatility_window=int(EXECUTION_CONFIG["volatility_window"]),
        target_volatility=float(EXECUTION_CONFIG["target_volatility"]),
        volatility_mode=str(EXECUTION_CONFIG["volatility_mode"]),
        enable_volatility_adjustment=bool(EXECUTION_CONFIG["enable_volatility_adjustment"]),
        cooldown_bars=int(EXECUTION_CONFIG["cooldown_bars"]),
        daily_momentum_limit=float(EXECUTION_CONFIG["daily_momentum_limit"]),
        weekly_momentum_limit=float(EXECUTION_CONFIG["weekly_momentum_limit"]),
        asset=meta["asset"],
        interval=interval,
        start_date=meta["start"],
        end_date=meta["end"],
        strategy_json=json.dumps(strategy_config),
        execution_config=EXECUTION_CONFIG,
    )

    try:
        result = run_backtest(request)
    finally:
        sys.stdout = _old_stdout
        _devnull.close()
    return result


# ---------------------------------------------------------------------------
# Combo plan builder + resume logic
# ---------------------------------------------------------------------------

def build_combo_plan(
    n_trigger: int,
    n_filter: int,
    trigger_signals: List[Dict],
    filter_signals: List[Dict],
) -> List[Tuple]:
    """
    Returns ordered list of (symbol_key, trigger_def, trigger_params, filter_def, filter_params).
    """
    plan = []
    for symbol_key in SYMBOLS:
        for trigger_def in trigger_signals:
            trigger_grid = build_param_grid(trigger_def, n_trigger)
            for trigger_params in trigger_grid:
                for filter_def in filter_signals:
                    filter_grid = build_param_grid(filter_def, n_filter)
                    for filter_params in filter_grid:
                        plan.append((symbol_key, trigger_def, trigger_params, filter_def, filter_params))
    return plan


def get_resume_index(output_path: str) -> int:
    """
    Returns the index of the next combo to run by reading the last completed
    run_id from the output CSV. Returns 0 if file doesn't exist or is empty.
    """
    if not os.path.exists(output_path):
        return 0
    try:
        df = pd.read_csv(output_path)
        if df.empty or "run_id" not in df.columns:
            return 0
        last_run_id = int(df["run_id"].max())
        print(f"[RESUME] Last completed run_id={last_run_id}. Resuming from run_id={last_run_id + 1}.")
        return last_run_id + 1
    except Exception as e:
        print(f"[RESUME] Could not read {output_path}: {e}. Starting fresh.")
        return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run signal permutation backtest sweep.")
    parser.add_argument("--n-trigger", type=int, default=3,
                        help="Total param combos per trigger signal (default: 3)")
    parser.add_argument("--n-filter",  type=int, default=3,
                        help="Total param combos per filter signal (default: 3)")
    parser.add_argument("--output",    type=str, default=DEFAULT_OUTPUT,
                        help=f"Output CSV path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--resume",    action="store_true",
                        help="Resume from last completed run in output CSV")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Print combo plan without running backtests")
    parser.add_argument("--symbols",   type=str, default=None,
                        help="Comma-separated subset of symbols to run (e.g. BTC,ETH)")
    parser.add_argument("--signals",   type=str, default="hardcoded",
                        choices=["hardcoded", "kb"],
                        help="Signal source: 'hardcoded' uses the curated lists in this file, "
                             "'kb' loads all numeric-param signals from signals_metadata.json (default: hardcoded)")
    parser.add_argument("--trigger-signals", type=str, default=None,
                        help="Comma-separated trigger signal names to include (filters whichever --signals source is active)")
    parser.add_argument("--filter-signals",  type=str, default=None,
                        help="Comma-separated filter signal names to include (filters whichever --signals source is active)")
    args = parser.parse_args()

    # Symbol filter
    symbols_to_run = list(SYMBOLS.keys())
    if args.symbols:
        requested = [s.strip().upper() for s in args.symbols.split(",")]
        invalid = [s for s in requested if s not in SYMBOLS]
        if invalid:
            print(f"ERROR: Unknown symbols: {invalid}. Valid: {list(SYMBOLS.keys())}")
            sys.exit(1)
        symbols_to_run = requested

    # Name filters
    trigger_name_filter = (
        [s.strip() for s in args.trigger_signals.split(",")]
        if args.trigger_signals else None
    )
    filter_name_filter = (
        [s.strip() for s in args.filter_signals.split(",")]
        if args.filter_signals else None
    )

    # Resolve signal lists
    if args.signals == "kb":
        print(f"[SWEEP] Loading signals from KB metadata: {SIGNALS_METADATA_PATH}")
        active_triggers = load_signals_from_metadata("TRIGGER", name_filter=trigger_name_filter)
        active_filters  = load_signals_from_metadata("FILTER",  name_filter=filter_name_filter)
        print(f"[SWEEP] KB signals loaded: {len(active_triggers)} triggers, {len(active_filters)} filters")
    else:
        active_triggers = TRIGGER_SIGNALS
        active_filters  = FILTER_SIGNALS
        if trigger_name_filter:
            active_triggers = [s for s in active_triggers if s["name"] in trigger_name_filter]
        if filter_name_filter:
            active_filters  = [s for s in active_filters  if s["name"] in filter_name_filter]

    if not active_triggers:
        print("ERROR: No trigger signals selected.")
        sys.exit(1)
    if not active_filters:
        print("ERROR: No filter signals selected.")
        sys.exit(1)

    # Build plan
    plan = build_combo_plan(args.n_trigger, args.n_filter, active_triggers, active_filters)
    plan = [(s, td, tp, fd, fp) for (s, td, tp, fd, fp) in plan if s in symbols_to_run]

    total = len(plan)
    print(f"[SWEEP] Plan: {len(symbols_to_run)} symbols x "
          f"{len(active_triggers)} triggers x "
          f"{len(active_filters)} filters = {total} total combos "
          f"(signals={args.signals})")
    print(f"[SWEEP] Output: {args.output}")

    if args.dry_run:
        print("\n[DRY RUN] First 10 combos:")
        for i, (sym, td, tp, fd, fp) in enumerate(plan[:10]):
            print(f"  {i:4d}  {sym:6s}  {td['name']:25s} {tp}  x  {fd['name']:20s} {fp}")
        if total > 10:
            print(f"  ... and {total - 10} more")
        print(f"\n[DRY RUN] Total: {total} combos. Exiting (no backtests run).")
        return

    # Resume offset
    start_idx = get_resume_index(args.output) if args.resume else 0
    if start_idx >= total:
        print(f"[SWEEP] All {total} combos already complete. Nothing to do.")
        return

    # Open CSV (append if resuming, write header if new)
    write_header = not args.resume or not os.path.exists(args.output) or start_idx == 0
    csv_file = open(args.output, "a" if args.resume else "w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=OUTPUT_COLUMNS)
    if write_header:
        writer.writeheader()
        csv_file.flush()

    print(f"[SWEEP] Starting from combo {start_idx}/{total}")

    # Pre-load all symbol DataFrames once
    print("[SWEEP] Pre-loading local CSV data...")
    symbol_dfs = {}
    for sym in symbols_to_run:
        print(f"  Loading {sym}...")
        symbol_dfs[sym] = load_local_csv(sym)
    print("[SWEEP] Data loaded.\n")

    completed = 0
    errors = 0

    for run_id, (symbol_key, trigger_def, trigger_params, filter_def, filter_params) in enumerate(plan):
        if run_id < start_idx:
            continue

        label = (f"[{run_id+1}/{total}] {symbol_key} | "
                 f"{trigger_def['name']} {trigger_params} x "
                 f"{filter_def['name']} {filter_params}")
        print(label, end=" ... ", flush=True)

        t0 = time.time()
        row = {
            "run_id":         run_id,
            "symbol":         symbol_key,
            "trigger_name":   trigger_def["name"],
            "trigger_params": json.dumps(trigger_params),
            "filter_name":    filter_def["name"],
            "filter_params":  json.dumps(filter_params),
            "timeframe":      SYMBOLS[symbol_key]["interval"],
            "start_date":     SYMBOLS[symbol_key]["start"].strftime("%Y-%m-%d"),
            "end_date":       SYMBOLS[symbol_key]["end"].strftime("%Y-%m-%d"),
            "timestamp":      datetime.utcnow().isoformat(),
        }

        try:
            result = run_single_backtest(
                symbol_key=symbol_key,
                trigger=trigger_def,
                trigger_params=trigger_params,
                filter_sig=filter_def,
                filter_params=filter_params,
                df_local=symbol_dfs[symbol_key],
            )

            if not result.get("success"):
                raise RuntimeError(result.get("error", "unknown error"))

            m = result.get("metrics", {})
            total_trades = int(m.get("total_trades") or 0)

            row.update({
                "total_trades":    total_trades,
                "win_rate":        round(float(m.get("win_rate") or 0), 4),
                "annual_return":   round(float(m.get("annual_return") or 0), 4),
                "sharpe_ratio":    round(float(m.get("sharpe_ratio") or 0), 4),
                "sortino_ratio":   round(float(m.get("sortino_ratio") or 0), 4),
                "max_drawdown":    round(float(m.get("max_drawdown") or 0), 4),
                "calmar_ratio":    round(float(m.get("calmar_ratio") or 0), 4),
                "net_pnl":         round(float((m.get("ending_balance") or 10000) - (m.get("starting_balance") or 10000)), 2),
                "starting_balance": float(m.get("starting_balance") or 10000),
                "ending_balance":   float(m.get("ending_balance") or 10000),
                "status":          "no_trades" if total_trades == 0 else "ok",
                "error_msg":       "",
            })
            completed += 1
            print(f"ok  trades={total_trades}  wr={row['win_rate']:.0%}  sharpe={row['sharpe_ratio']:.2f}  net={row['net_pnl']:+.0f}")

        except Exception as e:
            elapsed = round(time.time() - t0, 2)
            row.update({
                "total_trades": 0, "win_rate": 0, "annual_return": 0,
                "sharpe_ratio": 0, "sortino_ratio": 0, "max_drawdown": 0,
                "calmar_ratio": 0, "net_pnl": 0,
                "starting_balance": 10000, "ending_balance": 10000,
                "status":    "error",
                "error_msg": str(e)[:200],
            })
            errors += 1
            print(f"ERROR: {e}")
            traceback.print_exc()

        row["elapsed_seconds"] = round(time.time() - t0, 2)
        writer.writerow(row)
        csv_file.flush()

    csv_file.close()

    remaining = total - start_idx
    print(f"\n[SWEEP] Done. {completed}/{remaining} ok, {errors} errors.")
    print(f"[SWEEP] Results saved to: {args.output}")


if __name__ == "__main__":
    main()
