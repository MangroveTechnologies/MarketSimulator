# Running Experiments via CLI

All experiment lifecycle operations use the REST API at `http://localhost:5100/api/v1`.

## Prerequisites

```bash
# Start the container (from MarketSimulator directory)
docker compose up -d

# Verify it's running
curl -s http://localhost:5100/api/v1/datasets | python3 -m json.tool
```

The container startup generates signals metadata and daily companion OHLCV files
automatically. Check logs with `docker logs mangrove-sweep`.

## 1. List Available Datasets

```bash
curl -s http://localhost:5100/api/v1/datasets | python3 -m json.tool
```

Each dataset has: `asset`, `timeframe`, `file`, `rows`, `start_date`, `end_date`.
Daily companion files (e.g., `paxg_..._1d.csv`) are auto-generated from sub-daily
sources and appear as separate datasets.

## 2. List Available Signals

```bash
# All signals
curl -s http://localhost:5100/api/v1/signals | python3 -m json.tool

# Filter by type
curl -s 'http://localhost:5100/api/v1/signals?type=TRIGGER' | python3 -m json.tool
curl -s 'http://localhost:5100/api/v1/signals?type=FILTER' | python3 -m json.tool

# Search by name
curl -s 'http://localhost:5100/api/v1/signals?search=rsi' | python3 -m json.tool
```

## 3. Create an Experiment

```bash
curl -s -X POST http://localhost:5100/api/v1/experiments \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-experiment",
    "seed": 42,
    "search_mode": "random",
    "n_random": 10,
    "datasets": [
      {
        "asset": "PAXG",
        "timeframe": "1h",
        "file": "paxg_2025-01-01_2026-02-14_1h.csv",
        "rows": 9805,
        "start_date": "2025-01-01",
        "end_date": "2026-02-14"
      }
    ],
    "entry_signals": {"triggers": [], "filters": []},
    "exit_signals": {"triggers": [], "filters": []},
    "random_signals": {
      "n_entry_triggers": 1,
      "min_entry_filters": 1,
      "max_entry_filters": 2,
      "min_exit_triggers": 0,
      "max_exit_triggers": 1,
      "min_exit_filters": 0,
      "max_exit_filters": 1,
      "n_param_draws": 1
    },
    "execution_config": {
      "base": {},
      "sweep_axes": []
    },
    "workers_per_dataset": 1
  }'
```

Returns `experiment_id` -- save this for subsequent calls.

### Key Config Fields

| Field | Description |
|-------|-------------|
| `seed` | RNG seed for deterministic plans (same seed = same plan) |
| `search_mode` | `random` (sample N runs) or `grid` (enumerate all combos) |
| `n_random` | Number of random runs per dataset (random mode only) |
| `datasets` | Which OHLCV files to run against (copy from datasets endpoint) |
| `random_signals` | How many triggers/filters to draw per run |
| `min_entry_filters` | Must be >= 1 (engine requires at least 1 filter) |
| `workers_per_dataset` | Parallel workers per dataset (1 is fine for small runs) |
| `execution_config.base` | Override trading defaults (empty = use defaults) |
| `execution_config.sweep_axes` | List of param sweep axes for grid exploration |

## 4. Validate

```bash
curl -s -X POST "http://localhost:5100/api/v1/experiments/${EXP_ID}/validate"
```

Returns `total_runs` and any validation errors/warnings.

## 5. Launch

```bash
curl -s -X POST "http://localhost:5100/api/v1/experiments/${EXP_ID}/launch"
```

Returns worker count and total runs. Workers execute in background processes.

## 6. Check Progress

```bash
curl -s "http://localhost:5100/api/v1/experiments/${EXP_ID}/progress"
```

## 7. Query Results

```bash
# All results (paginated)
curl -s "http://localhost:5100/api/v1/experiments/${EXP_ID}/results" | python3 -m json.tool

# Sort by metric
curl -s "http://localhost:5100/api/v1/experiments/${EXP_ID}/results?sort=sharpe_ratio&order=desc"

# Filter
curl -s "http://localhost:5100/api/v1/experiments/${EXP_ID}/results?status=ok&min_trades=5"

# Quick summary
curl -s "http://localhost:5100/api/v1/experiments/${EXP_ID}/results" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for r in data['results']:
    print(f'Run {r[\"run_index\"]}: {r[\"trigger_name\"]} | trades={r[\"total_trades\"]} | return={r[\"total_return\"]:.2%} | sharpe={r[\"sharpe_ratio\"]:.2f} | status={r[\"status\"]}')
"
```

## 8. Visualize a Run

Re-runs the backtest and returns trade history + OHLCV for charting:

```bash
curl -s "http://localhost:5100/api/v1/experiments/${EXP_ID}/results/1/visualize" | python3 -c "
import sys, json
data = json.load(sys.stdin)
m = data.get('metrics', {})
print(f'Trades: {m.get(\"total_trades\",0)} | Sharpe: {m.get(\"sharpe_ratio\",0):.2f} | Balance: {m.get(\"ending_balance\",0):.2f}')
for t in data.get('trades', [])[:5]:
    print(f'  {t[\"entry_timestamp\"]} -> {t[\"exit_timestamp\"]} | {t[\"side\"]} | PnL: {t[\"profit_loss\"]:.2f} | {t[\"exit_reason\"]}')
"
```

## 9. Pause / Resume

```bash
# Pause
curl -s -X POST "http://localhost:5100/api/v1/experiments/${EXP_ID}/pause"

# Resume (re-launch -- skips already-completed runs)
curl -s -X POST "http://localhost:5100/api/v1/experiments/${EXP_ID}/launch"
```

## 10. List All Experiments

```bash
curl -s http://localhost:5100/api/v1/experiments | python3 -m json.tool
```

## Adding New OHLCV Data

1. Place CSV in `data/ohlcv/` following the naming convention:
   `{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv`

2. CSV format: `timestamp,open,high,low,close,volume` with UTC timestamps

3. Restart the container -- daily companions are auto-generated at startup:
   ```bash
   docker compose restart
   ```

4. Or generate manually without restart:
   ```bash
   docker exec mangrove-sweep python scripts/generate_daily_companions.py data/ohlcv
   ```

## Notes

- The first ~14 days of any sub-daily backtest are warmup (ATR needs 14 daily bars).
  No trades execute during warmup. This is normal.
- All data comes from local CSV files. No CoinAPI calls during experiments.
- Same seed + same config = deterministic results (reproducible).
- The UI at http://localhost:5100 provides the same functionality with charts.
