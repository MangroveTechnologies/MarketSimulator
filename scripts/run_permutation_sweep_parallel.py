"""
Parallel backtesting signal permutation sweep.

Splits work across 12 workers (2 per symbol) and writes chunk-based CSV files
to ``sweep_results/{SYMBOL}/worker_{id}_chunk_{n}.csv`` (1024 rows per chunk).

Supports deterministic resume: on restart, each worker counts its completed
rows and skips forward in its combo plan.

Lives in MarketSimulator but depends on MangroveAI's backtest engine at runtime.
Run inside an isolated container with both projects mounted::

    docker run -d --name mangrove-sweep \
        --network mangrove-network \
        -v /path/to/MangroveAI/src/MangroveAI:/app/MangroveAI \
        -v /path/to/MarketSimulator:/app/MarketSimulator \
        -e OMP_NUM_THREADS=1 \
        -e OPENBLAS_NUM_THREADS=1 \
        -e MKL_NUM_THREADS=1 \
        -e ENVIRONMENT=local \
        -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys/google_credentials.json \
        mangroveai-mangrove-app sleep infinity

    docker exec -w /app/MarketSimulator/scripts mangrove-sweep \
        python run_permutation_sweep_parallel.py [OPTIONS]

Usage examples::

    # Dry run: show combo plan
    python run_permutation_sweep_parallel.py --dry-run

    # Full run (all symbols, all signals)
    python run_permutation_sweep_parallel.py

    # Resume after interruption
    python run_permutation_sweep_parallel.py --resume

    # Restrict to specific symbols
    python run_permutation_sweep_parallel.py --symbols BTC,ETH

    # Use KB signals instead of hardcoded
    python run_permutation_sweep_parallel.py --signals kb
"""

import argparse
import csv
import json
import os
import sys
import time
import traceback
from datetime import datetime
from multiprocessing import Pool, current_process
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Pin BLAS threads before any numpy/pandas import in workers
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

sys.path.insert(0, "/app")

# Suppress noisy loggers
import logging as _logging
for _noisy in [
    "MangroveAI.domains.backtesting",
    "MangroveAI.domains.strategies",
    "MangroveAI.domains.managers",
    "MangroveAI.domains.positions",
]:
    _logging.getLogger(_noisy).setLevel(_logging.WARNING)

# Import the single-threaded sweep's infrastructure
from run_permutation_sweep import (
    SYMBOLS,
    TRIGGER_SIGNALS,
    FILTER_SIGNALS,
    EXECUTION_CONFIG,
    build_param_grid,
    load_local_csv,
    run_single_backtest,
    load_signals_from_metadata,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WORKERS_PER_SYMBOL = 2
CHUNK_SIZE = 1024
DEFAULT_OUTPUT_DIR = "/app/MarketSimulator/data/sweep_results"

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
    "gain_to_pain_ratio",
    "irr_annualized",
    "irr_daily",
    "avg_daily_return",
    "max_consecutive_wins",
    "max_consecutive_losses",
    "max_drawdown_duration",
    "num_days",
    "net_pnl",
    "starting_balance",
    "ending_balance",
    "status",
    "error_msg",
    "elapsed_seconds",
    "timestamp",
]


# ---------------------------------------------------------------------------
# Combo plan builder (symbol-level)
# ---------------------------------------------------------------------------

def build_symbol_plan(
    symbol_key: str,
    n_trigger: int,
    n_filter: int,
    trigger_signals: List[Dict],
    filter_signals: List[Dict],
    seed: int = 42,
) -> List[Tuple]:
    """Build the combo plan for a single symbol.

    Returns list of (trigger_def, trigger_params, filter_def, filter_params).
    The plan is deterministic given the same seed and signal lists.
    """
    rng = np.random.default_rng(seed)
    plan = []
    for trigger_def in trigger_signals:
        trigger_grid = build_param_grid(trigger_def, n_trigger)
        for trigger_params in trigger_grid:
            for filter_def in filter_signals:
                filter_grid = build_param_grid(filter_def, n_filter)
                for filter_params in filter_grid:
                    plan.append((trigger_def, trigger_params, filter_def, filter_params))
    # Shuffle deterministically so workers get a mix of fast/slow combos
    rng.shuffle(plan)
    return plan


def split_plan(plan: List, n_workers: int) -> List[List]:
    """Split a plan into n_workers roughly equal chunks (round-robin)."""
    splits = [[] for _ in range(n_workers)]
    for i, item in enumerate(plan):
        splits[i % n_workers].append(item)
    return splits


# ---------------------------------------------------------------------------
# Resume: count completed rows for a worker
# ---------------------------------------------------------------------------

def count_completed_rows(output_dir: str, symbol: str, worker_id: int) -> int:
    """Count total data rows across all chunk files for a worker."""
    symbol_dir = os.path.join(output_dir, symbol)
    if not os.path.isdir(symbol_dir):
        return 0
    total = 0
    chunk_idx = 0
    while True:
        path = os.path.join(symbol_dir, f"worker_{worker_id}_chunk_{chunk_idx}.csv")
        if not os.path.exists(path):
            break
        # Count lines minus header
        with open(path) as f:
            lines = sum(1 for _ in f) - 1  # subtract header
            total += max(0, lines)
        chunk_idx += 1
    return total


# ---------------------------------------------------------------------------
# Worker function
# ---------------------------------------------------------------------------

def worker_fn(args: Dict[str, Any]) -> Dict[str, Any]:
    """Run a subset of the combo plan for one symbol.

    Args:
        args: Dict with keys: worker_id, symbol_key, combos, output_dir,
              resume, n_trigger, n_filter.

    Returns:
        Dict with worker_id, symbol, completed, errors, skipped.
    """
    worker_id = args["worker_id"]
    symbol_key = args["symbol_key"]
    combos = args["combos"]
    output_dir = args["output_dir"]
    resume = args["resume"]

    symbol_dir = os.path.join(output_dir, symbol_key)
    os.makedirs(symbol_dir, exist_ok=True)

    # Resume: skip already-completed rows
    skip_count = 0
    if resume:
        skip_count = count_completed_rows(output_dir, symbol_key, worker_id)
        if skip_count > 0:
            print(
                f"[Worker {worker_id}] {symbol_key}: resuming, "
                f"skipping {skip_count}/{len(combos)} completed rows",
                flush=True,
            )

    if skip_count >= len(combos):
        print(
            f"[Worker {worker_id}] {symbol_key}: all {len(combos)} combos done.",
            flush=True,
        )
        return {
            "worker_id": worker_id,
            "symbol": symbol_key,
            "completed": 0,
            "errors": 0,
            "skipped": skip_count,
        }

    # Load data once for this symbol
    import pandas as pd
    df_local = load_local_csv(symbol_key)
    meta = SYMBOLS[symbol_key]

    completed = 0
    errors = 0
    row_buffer = []

    # Figure out which chunk to start writing to
    chunk_idx = skip_count // CHUNK_SIZE
    rows_in_current_chunk = skip_count % CHUNK_SIZE

    # If resuming mid-chunk, we need to append to the existing chunk
    if resume and rows_in_current_chunk > 0:
        # The partial chunk already has rows_in_current_chunk rows
        # We'll start a new chunk after it
        chunk_idx += 1
        rows_in_current_chunk = 0

    def flush_chunk(buffer: List[Dict], c_idx: int) -> int:
        """Write buffer to a chunk file and return the next chunk index."""
        path = os.path.join(symbol_dir, f"worker_{worker_id}_chunk_{c_idx}.csv")
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(buffer)
        return c_idx + 1

    total_combos = len(combos)
    for combo_idx, (trigger_def, trigger_params, filter_def, filter_params) in enumerate(combos):
        run_id = combo_idx  # global combo index within this worker's plan

        if combo_idx < skip_count:
            continue

        t0 = time.time()
        row = {
            "run_id": run_id,
            "symbol": symbol_key,
            "trigger_name": trigger_def["name"],
            "trigger_params": json.dumps(trigger_params),
            "filter_name": filter_def["name"],
            "filter_params": json.dumps(filter_params),
            "timeframe": meta["interval"],
            "start_date": meta["start"].strftime("%Y-%m-%d"),
            "end_date": meta["end"].strftime("%Y-%m-%d"),
            "timestamp": datetime.utcnow().isoformat(),
        }

        try:
            result = run_single_backtest(
                symbol_key=symbol_key,
                trigger=trigger_def,
                trigger_params=trigger_params,
                filter_sig=filter_def,
                filter_params=filter_params,
                df_local=df_local,
            )

            if not result.get("success"):
                raise RuntimeError(result.get("error", "unknown error"))

            m = result.get("metrics", {})
            total_trades = int(m.get("total_trades") or 0)

            row.update({
                "total_trades": total_trades,
                "win_rate": round(float(m.get("win_rate") or 0), 4),
                "annual_return": round(float(m.get("annual_return") or 0), 4),
                "sharpe_ratio": round(float(m.get("sharpe_ratio") or 0), 4),
                "sortino_ratio": round(float(m.get("sortino_ratio") or 0), 4),
                "max_drawdown": round(float(m.get("max_drawdown") or 0), 4),
                "calmar_ratio": round(float(m.get("calmar_ratio") or 0), 4),
                "gain_to_pain_ratio": round(float(m.get("gain_to_pain_ratio") or 0), 4),
                "irr_annualized": round(float(m.get("irr_annualized") or 0), 4),
                "irr_daily": round(float(m.get("irr_daily") or 0), 6),
                "avg_daily_return": round(float(m.get("avg_daily_return") or 0), 6),
                "max_consecutive_wins": int(m.get("max_consecutive_wins") or 0),
                "max_consecutive_losses": int(m.get("max_consecutive_losses") or 0),
                "max_drawdown_duration": int(m.get("max_drawdown_duration") or 0),
                "num_days": int(m.get("num_days") or 0),
                "net_pnl": round(float((m.get("ending_balance") or 10000) - (m.get("starting_balance") or 10000)), 2),
                "starting_balance": float(m.get("starting_balance") or 10000),
                "ending_balance": float(m.get("ending_balance") or 10000),
                "status": "no_trades" if total_trades == 0 else "ok",
                "error_msg": "",
            })
            completed += 1

        except Exception as e:
            row.update({
                "total_trades": 0, "win_rate": 0, "annual_return": 0,
                "sharpe_ratio": 0, "sortino_ratio": 0, "max_drawdown": 0,
                "calmar_ratio": 0, "gain_to_pain_ratio": 0,
                "irr_annualized": 0, "irr_daily": 0, "avg_daily_return": 0,
                "max_consecutive_wins": 0, "max_consecutive_losses": 0,
                "max_drawdown_duration": 0, "num_days": 0,
                "net_pnl": 0, "starting_balance": 10000, "ending_balance": 10000,
                "status": "error",
                "error_msg": str(e)[:200],
            })
            errors += 1

        row["elapsed_seconds"] = round(time.time() - t0, 2)
        row_buffer.append(row)

        # Flush chunk when buffer is full
        if len(row_buffer) >= CHUNK_SIZE:
            chunk_idx = flush_chunk(row_buffer, chunk_idx)
            row_buffer = []
            done_so_far = combo_idx + 1
            print(
                f"[Worker {worker_id}] {symbol_key}: "
                f"{done_so_far}/{total_combos} "
                f"({done_so_far / total_combos * 100:.1f}%) "
                f"chunk {chunk_idx - 1} written",
                flush=True,
            )

    # Flush remaining rows
    if row_buffer:
        chunk_idx = flush_chunk(row_buffer, chunk_idx)
        print(
            f"[Worker {worker_id}] {symbol_key}: final chunk {chunk_idx - 1} "
            f"written ({len(row_buffer)} rows)",
            flush=True,
        )

    print(
        f"[Worker {worker_id}] {symbol_key}: DONE. "
        f"{completed} ok, {errors} errors, {skip_count} skipped",
        flush=True,
    )

    return {
        "worker_id": worker_id,
        "symbol": symbol_key,
        "completed": completed,
        "errors": errors,
        "skipped": skip_count,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Parallel signal permutation backtest sweep.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--n-trigger", type=int, default=3,
        help="Total param combos per trigger signal (default: 3)",
    )
    parser.add_argument(
        "--n-filter", type=int, default=3,
        help="Total param combos per filter signal (default: 3)",
    )
    parser.add_argument(
        "--output", type=str, default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--workers-per-symbol", type=int, default=WORKERS_PER_SYMBOL,
        help=f"Workers per symbol (default: {WORKERS_PER_SYMBOL})",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for combo plan shuffling (default: 42)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from existing chunk files",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print plan without running backtests",
    )
    parser.add_argument(
        "--symbols", type=str, default=None,
        help="Comma-separated subset of symbols (e.g. BTC,ETH)",
    )
    parser.add_argument(
        "--signals", type=str, default="hardcoded",
        choices=["hardcoded", "kb"],
        help="Signal source: hardcoded or kb (default: hardcoded)",
    )
    parser.add_argument(
        "--trigger-signals", type=str, default=None,
        help="Comma-separated trigger signal names to include",
    )
    parser.add_argument(
        "--filter-signals", type=str, default=None,
        help="Comma-separated filter signal names to include",
    )
    args = parser.parse_args()

    # -----------------------------------------------------------------------
    # Resolve symbols
    # -----------------------------------------------------------------------
    symbols_to_run = list(SYMBOLS.keys())
    if args.symbols:
        requested = [s.strip().upper() for s in args.symbols.split(",")]
        invalid = [s for s in requested if s not in SYMBOLS]
        if invalid:
            print(f"ERROR: Unknown symbols: {invalid}. Valid: {list(SYMBOLS.keys())}")
            sys.exit(1)
        symbols_to_run = requested

    # -----------------------------------------------------------------------
    # Resolve signals
    # -----------------------------------------------------------------------
    trigger_name_filter = (
        [s.strip() for s in args.trigger_signals.split(",")]
        if args.trigger_signals else None
    )
    filter_name_filter = (
        [s.strip() for s in args.filter_signals.split(",")]
        if args.filter_signals else None
    )

    if args.signals == "kb":
        print(f"[SWEEP] Loading signals from KB metadata")
        active_triggers = load_signals_from_metadata("TRIGGER", name_filter=trigger_name_filter)
        active_filters = load_signals_from_metadata("FILTER", name_filter=filter_name_filter)
        print(f"[SWEEP] KB signals: {len(active_triggers)} triggers, {len(active_filters)} filters")
    else:
        active_triggers = TRIGGER_SIGNALS
        active_filters = FILTER_SIGNALS
        if trigger_name_filter:
            active_triggers = [s for s in active_triggers if s["name"] in trigger_name_filter]
        if filter_name_filter:
            active_filters = [s for s in active_filters if s["name"] in filter_name_filter]

    if not active_triggers:
        print("ERROR: No trigger signals selected.")
        sys.exit(1)
    if not active_filters:
        print("ERROR: No filter signals selected.")
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Build per-symbol plans and assign workers
    # -----------------------------------------------------------------------
    n_workers = args.workers_per_symbol
    worker_tasks = []
    global_worker_id = 0
    total_combos = 0

    for symbol_key in symbols_to_run:
        plan = build_symbol_plan(
            symbol_key=symbol_key,
            n_trigger=args.n_trigger,
            n_filter=args.n_filter,
            trigger_signals=active_triggers,
            filter_signals=active_filters,
            seed=args.seed,
        )
        total_combos += len(plan)
        splits = split_plan(plan, n_workers)

        for split_idx, worker_combos in enumerate(splits):
            worker_tasks.append({
                "worker_id": global_worker_id,
                "symbol_key": symbol_key,
                "combos": worker_combos,
                "output_dir": args.output,
                "resume": args.resume,
            })
            global_worker_id += 1

    total_workers = len(worker_tasks)

    print(f"[SWEEP] {len(symbols_to_run)} symbols x "
          f"{len(active_triggers)} triggers x {len(active_filters)} filters")
    print(f"[SWEEP] {total_combos} total combos across {total_workers} workers "
          f"({n_workers} per symbol)")
    print(f"[SWEEP] Output: {args.output}")
    print(f"[SWEEP] Chunk size: {CHUNK_SIZE} rows")

    # -----------------------------------------------------------------------
    # Dry run
    # -----------------------------------------------------------------------
    if args.dry_run:
        print(f"\n[DRY RUN] Worker assignments:")
        for wt in worker_tasks:
            completed = count_completed_rows(
                args.output, wt["symbol_key"], wt["worker_id"]
            ) if args.resume else 0
            print(
                f"  Worker {wt['worker_id']:2d}  {wt['symbol_key']:6s}  "
                f"{len(wt['combos']):6d} combos"
                + (f"  ({completed} done)" if completed > 0 else "")
            )
        print(f"\n[DRY RUN] Total: {total_combos} combos. Exiting.")
        return

    # -----------------------------------------------------------------------
    # Run parallel workers
    # -----------------------------------------------------------------------
    print(f"\n[SWEEP] Launching {total_workers} workers...\n", flush=True)
    t0 = time.time()

    with Pool(processes=total_workers) as pool:
        results = pool.map(worker_fn, worker_tasks)

    elapsed = time.time() - t0
    hours = elapsed / 3600

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    total_completed = sum(r["completed"] for r in results)
    total_errors = sum(r["errors"] for r in results)
    total_skipped = sum(r["skipped"] for r in results)

    print(f"\n{'=' * 60}")
    print(f"[SWEEP] COMPLETE")
    print(f"  Elapsed:   {hours:.2f} hours ({elapsed:.0f}s)")
    print(f"  Completed: {total_completed}")
    print(f"  Errors:    {total_errors}")
    print(f"  Skipped:   {total_skipped}")
    print(f"  Rate:      {total_completed / max(elapsed, 1):.1f} combos/sec")
    print(f"  Output:    {args.output}")
    print(f"{'=' * 60}")

    for r in results:
        print(
            f"  Worker {r['worker_id']:2d}  {r['symbol']:6s}  "
            f"done={r['completed']}  err={r['errors']}  skip={r['skipped']}"
        )


if __name__ == "__main__":
    main()
