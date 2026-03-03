# MarketSimulator

Research and experimentation platform under the Mangrove portfolio. Read the parent [CLAUDE.md](../CLAUDE.md) for the full project landscape.

## Workstreams

### 1. Agent-Based Market Simulator (research)
- MDP framework, 5 agent types, square-root impact model
- Generates synthetic OHLCV data for BTC, XAU, META, CL
- Lives in `market_simulator.ipynb` and `market-simulator.md`
- Fully functional but not yet extracted to a Python module

### 2. Legacy Permutation Sweep (paused, superseded)
- Old v1 CSV-based sweep: 12 parallel workers, chunk-based CSV output
- Entry point: `scripts/run_permutation_sweep_parallel.py`
- **Superseded by the Experiment Framework** (Workstream 4). Code preserved for reference.
- Old results cleared. Do not run new sweeps with this code.

### 3. LLM Copilot Benchmark
- 3-agent design: user agent (gpt-4.1-nano), copilot under test, judge (claude-sonnet-4-6)
- Scores 7 criteria: intent, signal selection, parameters, conversation, guardrails, efficiency, error recovery
- **Status**: Fully coded, not yet run. Needs first dry-run.
- Entry point: `scripts/benchmark/run_benchmark.py`

### 4. Experiment Framework (active, primary workstream)
- FastAPI backend + React frontend for running, exploring, and visualizing backtest experiments
- Parquet + DuckDB storage, chunked workers, Redis progress streaming
- Container: `mangrove-sweep` on port 5100
- Entry point: `docker compose up -d` from this directory

## Container Architecture

The `mangrove-sweep` container mounts three sibling projects:

| Mount | Container Path | Purpose |
|-------|---------------|---------|
| `MangroveAI/src/MangroveAI` | `/app/MangroveAI` | Backtest engine (runtime dependency) |
| `MangroveAI/.git` | `/app/MangroveAI/.git` | Version tracking (read-only) |
| `MangroveKnowledgeBase` | `/app/MangroveKnowledgeBase` | Signals package (installed from source at startup) |
| `MarketSimulator` (this repo) | `/app/MarketSimulator` | Experiment server, UI, scripts, data |

**Startup sequence** (docker-compose.yml command):
1. `git config --global --add safe.directory` for both repos
2. `pip install` runtime deps (fastapi, duckdb, etc.)
3. `pip install --no-deps /app/MangroveKnowledgeBase` (latest source, not stale PyPI)
4. `python scripts/generate_signals_metadata.py` (generates `data/signals_metadata.json` from mangrove_kb)
5. `python scripts/generate_daily_companions.py` (resamples sub-daily CSVs to daily for ATR)
6. `uvicorn experiment_server.app:app` on port 5100

## Key Conventions

- **BLAS thread pinning** -- always set OMP/OPENBLAS/MKL_NUM_THREADS=1 in container env
- **Parquet chunks** -- experiment framework writes Parquet chunks per worker (not CSV)
- **Seed determinism** -- `experiment_seed * 1000000 + run_index` for per-run RNG
- **Logger suppression** -- backtesting/strategies/managers/positions loggers set to WARNING
- **stdout suppression** -- backtest engine print() redirected to /dev/null during sweep
- **OHLCV injection** -- both sweep workers and visualize service inject local CSVs (signal TF + daily companion) into `_OHLCV_CACHE` via shared utility (`ohlcv_utils.py`). Cache keys match the engine's exact lookup pattern (asset with -USDT, ATR pre-history date offsets). No monkeypatching, no CoinAPI calls.
- **Daily companions** -- generated at startup by `scripts/generate_daily_companions.py` (resamples sub-daily CSVs to daily OHLCV). Required because the engine needs both signal TF and 1D for ATR calculations.
- **Code version** -- provenance tracks both repos: `ms:<hash> ai:<hash>`
- **Signals metadata** -- generated at startup from `mangrove_kb` source, never a static copy

## Project Structure

```
config/                     # Trading defaults (moved from data/)
  trading_defaults.json
data/                       # Runtime data (gitignored)
  ohlcv/                    # Input OHLCV CSVs + daily companions (auto-generated)
  experiments/              # Experiment results (Parquet)
  signals_metadata.json     # Generated at startup
docker-compose.yml          # Container definition
experiment_server/          # FastAPI backend
  app.py                    # App entry point
  config.py                 # Settings (env vars with EXP_ prefix)
  routes/                   # API endpoints (experiments, results, signals, etc.)
  services/                 # Business logic (executor, query, visualize, etc.)
  workers/                  # Sweep worker, Parquet writer
  models/                   # Pydantic models
experiment_ui/              # React frontend (Vite + Tailwind)
  src/views/                # ExploreView, ViewTab, ConfigureView, MonitorView
experiment_ui_dist/         # Built frontend (gitignored)
scripts/                    # Legacy sweep, benchmark, metadata generation
  benchmark/                # LLM copilot benchmark (9 modules)
  generate_signals_metadata.py  # Startup metadata generation
```

## Metrics Engine (MangroveAI)

Post-simulation metrics computed in `MangroveAI/utils/metrics.py`:
- **Sortino ratio** -- capped at 9999.9; returns 9999.9 when no downside and avg_return > 0
- **Calmar ratio** -- epsilon floor of 0.0001 on max_drawdown denominator, capped at 9999.9
- **Daily sampling** -- `ticks_per_day` calculated dynamically from timeframe (not hardcoded to 24)
- **IRR** -- `numpy_financial.irr()` on daily cash flows; annualized via `(1 + irr_daily)^365 - 1`

The visualize endpoint re-runs backtests and returns **fresh metrics** (not stored Parquet values).

## What NOT to Do

- Don't keep static copies of `signals_metadata.json` -- it's generated at startup
- Don't hardcode container paths outside of scripts (they use `/app/` prefix)
- Don't call CoinAPI -- all data is loaded from local CSVs via `_OHLCV_CACHE` injection
- Don't change `EXECUTION_CONFIG` in sweep scripts without documenting why (it affects all results)
- Don't run the benchmark without MangroveAI postgres running
- Don't commit anything under `data/`, `venv/`, `experiment_ui_dist/`, or `__pycache__/`
