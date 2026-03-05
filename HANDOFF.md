# MarketSimulator -- Handoff Document

Last updated: 2026-03-05

## What Works

- **Single data path from local files** -- sweep workers and visualize both use `_OHLCV_CACHE` injection via `ohlcv_utils.py`. No CoinAPI calls. Cache keys match the engine's exact lookup pattern.
- **Daily companion files** -- auto-generated at startup from sub-daily CSVs. Required for ATR (engine needs signal TF + 1D).
- **Multi-stage Dockerfile** -- `docker compose up --build -d` is one command. Node builds frontend, Python image runs server. No manual `npm run build` step.
- **Experiment lifecycle** -- create, validate, launch, pause, resume via REST API.
- **Auto-completion detection** -- experiments transition from "running" to "completed" when all runs finish, or "failed" if no results after 5 minutes.
- **Random search mode** -- fully working in UI and API.
- **Visualize endpoint** -- re-runs backtests from Parquet, returns trades + OHLCV. Results match sweep results exactly.
- **Pagination** -- default 100 rows, selector for 50/100/200/500.
- **Dark/light theme** -- both work. Light theme has proper card shadows and stronger borders.
- **SL/TP fill at order price** -- MangroveAI fix (trade_manager.py), fills at the stop/take-profit price, not bar close.
- **ATR warmup handling** -- MangroveAI fix (strategies/services.py), logs and skips entry when insufficient data instead of crashing.

## What's Broken / Needs Fixing

### 1. Daily companion files show in dataset selection

**Problem:** The dataset discovery endpoint returns ALL CSVs in `data/ohlcv/`, including the auto-generated daily companions. Users see duplicate entries like "PAXG 1h" AND "PAXG 1d" when they only need to select the signal timeframe.

**Fix:** Either:
- Filter companions out of the discovery response (detect by matching `{asset}_{dates}_1d.csv` where a sub-daily file with the same prefix exists)
- Or automatically associate the daily companion when a sub-daily dataset is selected (don't show it as a separate selectable item)

**Files:** `experiment_server/services/dataset.py` (`discover_datasets` function)

### 2. Grid mode not available in UI

**Problem:** Selecting "Grid" in the configure view shows a placeholder message: "Grid mode requires selecting specific signals... available in the API but not yet in the UI."

**Backend status:** Grid mode is fully implemented (`plan_generator.py` has `_generate_grid_plan()`). The API works. Only the UI is missing.

**What the UI needs:**
- Signal selector: two-panel widget (available signals on left, selected on right)
- Per-signal parameter configuration (define sweep ranges per param)
- The UI/UX spec exists: `docs/plans/2026-03-01-experiment-framework-ui-ux.md` section 5.2

**Files:** `experiment_ui/src/views/ConfigureView.tsx` (lines 439-444 has the placeholder)

### 3. Execution config sweep axis UI may not be wired correctly

**Problem:** User reports sweep axis UI is missing. The UI was added (commit `87bab61`) but needs verification that:
- The sweep axes state actually gets passed through to `buildConfig()`
- The backend receives and processes the sweep axes
- The plan generator creates variant configs from the axes

**Verification steps:**
1. Open Configure view, add a sweep axis (e.g., atr_period min=10, max=20, n=3)
2. Create and validate experiment
3. Check that `total_runs` reflects the sweep axis multiplier
4. Launch and verify results have different atr_period values

**Files:** `experiment_ui/src/views/ConfigureView.tsx` (lines 149-163 for state, 471-544 for UI, ~197 for buildConfig)

### 4. Experiments in data/ not showing on frontend

**Problem:** 5 experiments exist in `data/experiments/` but user reports they don't appear. Possible causes:
- The container's `data/experiments/` might be empty (volume mount only maps `data/ohlcv/`, not `data/experiments/`)
- The `EXP_DATA_DIR` env var might not resolve correctly in the container
- The experiment list endpoint might be filtering them out

**Investigation:** Check `docker-compose.yml` volume mounts. The current setup mounts `./data/ohlcv:/app/MarketSimulator/data/ohlcv` but does NOT mount `./data/experiments`. The Dockerfile COPYs `data/ohlcv/` but not `data/experiments/`. Experiments created inside the container go to `/app/MarketSimulator/data/experiments/` which is ephemeral (lost on container rebuild).

**Fix:** Either:
- Add a volume mount for `./data/experiments:/app/MarketSimulator/data/experiments` in docker-compose.yml
- Or mount the entire data directory: `./data:/app/MarketSimulator/data`

**Files:** `docker-compose.yml` (volume mounts section)

### 5. sweep_results/ directory is empty and stale

**Problem:** `data/sweep_results/` is a leftover from the v1 permutation sweep (superseded by the experiment framework). It's empty and confusing.

**Fix:** Delete it. The experiment framework stores results in `data/experiments/{id}/results/`.

### 6. Frontend verification mandatory

**Problem:** Previous sessions made CSS/layout changes that appeared correct in code but were broken in the browser (a global CSS reset `* { margin: 0; padding: 0; }` was overriding all Tailwind utilities). This was only caught by inspecting computed styles via Playwright.

**Rule:** ALWAYS verify frontend changes using Playwright before claiming anything works. See CLAUDE.md "Frontend Verification (MANDATORY)" section for the exact steps.

## Uncommitted MangroveAI Changes

These changes exist locally in `../MangroveAI/src/MangroveAI/` but are NOT committed:

1. **strategies/services.py** -- ATR warmup: catch ValueError from insufficient ATR data, log at INFO with details, return None (skip entry). Affects both backtesting and live evaluation.

2. **managers/trade_manager.py** -- SL/TP fill price: set `fill_price = order.price` for STOP_LOSS and TAKE_PROFIT orders (was defaulting to `current_price` / bar close).

## MarketSimulator Commits (pushed to GitHub)

All changes are on `master` at `MangroveTechnologies/MarketSimulator`. Key commits:

| Commit | Description |
|--------|-------------|
| `5abe97b` | OHLCV single data path fix (ohlcv_utils.py, sweep worker, visualize) |
| `d09069f` | Imports cleanup, CLAUDE.md docs |
| `87bab61` | Experiment status auto-detection, pagination, sweep axis UI, CSS spacing |
| `b356d14` | CSS reset fix, multi-stage Dockerfile, light theme, failed experiment detection |

## Architecture Notes

- Container mounts MangroveAI and MangroveKnowledgeBase as sibling volumes
- Frontend is built inside Docker (multi-stage: Node -> Python) -- no manual npm build needed
- `docker compose up --build -d` is the single command to build and launch
- OHLCV data path: local CSV -> `_OHLCV_CACHE` injection -> engine reads from cache
- Daily companions are resampled from sub-daily CSVs (crypto 24/7 = lossless)
- First ~14 simulated days of any sub-daily backtest are ATR warmup (no trades)
- GCP credentials required for MangroveAI config loading (`gcloud auth application-default login`)

## File Layout

```
Dockerfile                  # Multi-stage: Node (frontend) + Python (runtime)
docker-compose.yml          # Container definition with volume mounts
CLAUDE.md                   # Project instructions (read this first)
experiment_server/          # FastAPI backend
  services/ohlcv_utils.py   # Shared OHLCV cache injection utility
  services/executor.py      # Experiment lifecycle + auto-completion
  services/visualize.py     # Backtest re-execution (uses cache injection, no monkeypatch)
  workers/sweep_worker.py   # Parallel backtest execution
experiment_ui/              # React frontend (Vite + Tailwind v4)
  src/views/ConfigureView   # Experiment configuration UI
  src/views/ExploreView     # Results table with inline expansion
  src/views/MonitorView     # Experiment list and progress
  src/views/ViewTab         # Trade visualization with OHLCV chart
scripts/
  generate_daily_companions.py  # Resamples sub-daily to daily OHLCV
  generate_signals_metadata.py  # Generates signal metadata from mangrove_kb
data/
  ohlcv/                    # 7 source CSVs + 6 daily companions
  experiments/              # Experiment configs + Parquet results
docs/
  running-experiments-cli.md  # CLI usage guide
  plans/                      # Design docs and specs
```
