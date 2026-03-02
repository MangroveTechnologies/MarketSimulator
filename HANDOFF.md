# MarketSimulator -- Handoff Document

Last updated: 2026-03-02

## Active Workstream: Experiment Framework

### What's Working

- **FastAPI backend** (port 5100) with full REST API -- 22 endpoints, 87+ tests
- **DuckDB + Parquet** storage for experiment results
- **Parallel worker execution** via multiprocessing with real MangroveAI backtest engine
- **Dashboard** at http://localhost:5100/ (React SPA, basic) and http://localhost:5100/old (HTML fallback)
- **7 OHLCV datasets** (BTC/1d, ETH/4h, DOGE/5m, LINK/30m, PAXG/1h, SOL/5m, XRP/15m)
- **96 signals** (34 triggers, 62 filters) from MangroveKnowledgeBase
- **Docker container** `mangrove-sweep` with `--restart unless-stopped`
- **config_hash** column in Parquet schema (SHA256 of full strategy config for dedup)
- **Dual search mode** -- random (sample N) and grid (enumerate all)
- **3 experiments** completed (70 runs) + 1 running ("seed", 300K runs)

### Known Backend Limitations

1. **config_hash stored but not checked** -- The hash is computed and written to Parquet
   per result row, but the worker does NOT check for duplicates before running. The dedup
   query (`SELECT 1 WHERE config_hash = ?`) needs to be added to the worker loop. This
   means duplicate configs CAN be run across experiments currently.

2. **Exit signal validation** -- MangroveAI's Strategy class requires exit rules to have
   exactly 1 TRIGGER if any exit signals are specified. The random plan generator can
   create exit configs with only FILTER signals (no trigger), causing ValueError. Fix:
   add constraint in `_generate_random_plan` to ensure exit always has a trigger when
   exit signals are present.

3. **Multi-filter entry limitation** -- MangroveAI's backtest engine only uses the first
   filter in entry when multiple are provided ("Entry has 2 filters, using only the first
   one"). The plan generator can create multi-filter entries, but only the first filter
   is actually evaluated. This is an engine limitation.

4. **win_rate stored as 0-100** -- The engine returns win_rate as a percentage (e.g., 60.0
   for 60%). Display code must NOT multiply by 100 again. The explore view computes this
   correctly now.

5. **total_return field** -- Fixed in worker to read `m.get("total_return")`. Old experiment
   data has 0.0 for this field. The explore view computes return on-the-fly from
   ending_balance and net_pnl to work around this.

6. **Provenance for old experiments** -- Experiments created before 2026-03-02 have empty
   data_file_hash and code_version. New experiments populate these correctly.

7. **Experiment status detection** -- Workers don't update experiment status to "completed"
   when done. Status was manually fixed for first experiments. Need auto-completion
   detection (check if completed count == total_runs).

### React Frontend Status

The React app at `experiment_ui/` is scaffolded with Vite + TypeScript + Tailwind but
needs significant work:

**Issues identified by user:**
- Color scheme is bad -- Tailwind v4 custom theme variables aren't rendering correctly
- Light theme toggle is broken
- Configure view is a placeholder (links to old HTML)
- Detail panel should expand inline (accordion), not below table
- Execution config display needs grouped sections, not one long table
- Missing interactive OHLCV chart with trade markers (lightweight-charts)
- Missing trades table tab
- Missing start/end dates, num_bars, file_hash, code_version in results display

**What needs to happen:**
1. Fix Tailwind v4 theme -- either fix `@theme` approach or use standard CSS variables
2. Rebuild Explore view with inline-expanding rows, grouped config, chart + trades tabs
3. Build Configure view (port from HTML dashboard with improvements)
4. Build Monitor view with real SSE progress streaming
5. Apply Mangrove brand properly (see `docs/plans/2026-03-01-experiment-framework-ui-ux.md`)

### Design Documents

All in `docs/plans/`:
- `2026-02-28-experiment-framework-requirements.md`
- `2026-02-28-experiment-framework-specification.md`
- `2026-02-28-experiment-framework-architecture.md`
- `2026-02-28-experiment-framework-implementation.md`
- `2026-03-01-experiment-framework-ui-ux.md`

### Brand Assets

In `branding/`: 5 SVG logos + `brand-guidelines.md`

### Container Setup

```bash
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

http://localhost:5100/docs
