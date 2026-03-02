# MarketSimulator -- Handoff Document

Last updated: 2026-03-02

## Active Workstream: Experiment Framework

### What's Working

- **FastAPI backend** (port 5100) with full REST API -- 22 endpoints, 87 tests passing
- **DuckDB + Parquet** storage for experiment results
- **Parallel worker execution** via multiprocessing with real MangroveAI backtest engine
- **Dashboard** at http://localhost:5100/ (React SPA) and http://localhost:5100/old (HTML fallback)
- **7 OHLCV datasets** (BTC/1d, ETH/4h, DOGE/5m, LINK/30m, PAXG/1h, SOL/5m, XRP/15m)
- **96 signals** (34 triggers, 62 filters) from MangroveKnowledgeBase
- **Docker container** `mangrove-sweep` with `--restart unless-stopped`
- **2 completed experiments** (70 total runs, 21 with trades)

### What Needs Finishing (React UI)

The React frontend at `experiment_ui/` is scaffolded but needs significant work.
Current state is a first pass that has major issues the user identified:

1. **Configure View** -- Currently a placeholder linking to old HTML. Needs full form with
   collapsible sections (datasets, search mode, signal counts, exec config sweeps, stats bar)

2. **Explore View** -- Has results table and detail panel but:
   - Row detail should **expand inline** (accordion style), not show below the table
   - Execution config display needs **grouped sections** (risk, volatility, timing, etc.), not one long table
   - Missing **interactive chart** with OHLCV candles + trade entry/exit markers (use lightweight-charts)
   - Missing **trades table** tab showing individual trade records
   - Color scheme doesn't match brand properly -- Tailwind v4 CSS variable approach needs fixing
   - Light theme toggle is broken
   - Needs start/end dates, num_bars, data_file_hash, code_version shown prominently

3. **Monitor View** -- Basic experiment list exists but:
   - No real-time progress (SSE not wired)
   - No per-dataset progress bars
   - No rate/ETA display
   - No pause/resume controls

4. **Styling** -- The custom Tailwind colors (`mg-*`) aren't rendering correctly in Tailwind v4.
   Need to verify the `@theme` approach works or switch to standard CSS variables.

### Design Documents

All in `docs/plans/`:
- `2026-02-28-experiment-framework-requirements.md` -- Approved
- `2026-02-28-experiment-framework-specification.md` -- Approved
- `2026-02-28-experiment-framework-architecture.md` -- Approved
- `2026-02-28-experiment-framework-implementation.md` -- Implementation plan (29 tasks)
- `2026-03-01-experiment-framework-ui-ux.md` -- UI/UX design with Mangrove brand spec
- `docs/data-model-exploration.md` -- Parquet schema mapping

### Brand Assets

In `branding/`:
- 5 SVG logo variants
- `brand-guidelines.md` -- Color palette, typography, logo rules

### Known Data Issues

- **Existing experiment results** have `total_return=0` (bug fixed in worker, needs re-run for correct data)
- **Existing results** have empty `data_file_hash` and `code_version` (fixed for new experiments)
- **win_rate** is stored as 0-100 (percentage), not 0-1 -- display code must NOT multiply by 100

### Container Setup

```bash
# Container is already running with --restart unless-stopped
docker ps | grep mangrove-sweep

# If not running:
docker run -d --name mangrove-sweep \
    --restart unless-stopped \
    --network mangrove-network \
    -v /path/to/MangroveAI/src/MangroveAI:/app/MangroveAI \
    -v /path/to/MarketSimulator:/app/MarketSimulator \
    -p 5100:5100 \
    -e OMP_NUM_THREADS=1 -e OPENBLAS_NUM_THREADS=1 -e MKL_NUM_THREADS=1 \
    -e ENVIRONMENT=local \
    -e EXP_DATA_DIR=/app/MarketSimulator/data \
    -e EXP_OHLCV_DIR=/app/MarketSimulator/data/ohlcv \
    -e EXP_SIGNALS_METADATA_PATH=/app/MarketSimulator/data/signals_metadata.json \
    -e EXP_TRADING_DEFAULTS_PATH=/app/MarketSimulator/data/trading_defaults.json \
    mangroveai-mangrove-app \
    bash -c "pip install -q fastapi uvicorn duckdb pyarrow pydantic pydantic-settings redis rq && \
             git config --global --add safe.directory /app/MarketSimulator && \
             cd /app/MarketSimulator && uvicorn experiment_server.app:app --host 0.0.0.0 --port 5100"
```

### React Dev Workflow

```bash
cd experiment_ui
npm install
npm run dev          # Dev server on :5200 with proxy to :5100
npm run build        # Builds to ../experiment_ui_dist/ (served by FastAPI)
```

### API Docs

http://localhost:5100/docs (auto-generated FastAPI OpenAPI)
