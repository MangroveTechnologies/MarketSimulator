# MarketSimulator -- Handoff Document

Last updated: 2026-03-03

## Active Workstream: Experiment Framework

### What's Working

- **FastAPI backend** (port 5100) with full REST API -- 22 endpoints
- **DuckDB + Parquet** storage for experiment results
- **Parallel worker execution** via multiprocessing with real MangroveAI backtest engine
- **React SPA dashboard** at http://localhost:5100/ with 3 views:
  - **Explore** -- results table with inline detail expansion, OHLCV chart (lightweight-charts v5), trades tab
  - **Monitor** -- experiment list, progress bars, pause/resume controls, dataset breakdown
  - **Configure** -- collapsible sections, dataset selector, signal config, execution config editor
- **Visualize endpoint** -- re-runs backtests from stored Parquet data to produce trade history + OHLCV candles
- **Single data path from local files** -- both sweep and visualize use `_OHLCV_CACHE` injection via shared `ohlcv_utils.py`. No monkeypatching, no CoinAPI calls.
- **Daily companion files** -- auto-generated at startup by resampling sub-daily CSVs to daily OHLCV (required for ATR baseline calculations)
- **7 OHLCV datasets** (BTC/1d, ETH/4h, DOGE/5m, LINK/30m, PAXG/1h, SOL/5m, XRP/15m) + 6 daily companions
- **96 signals** (34 triggers, 62 filters) from MangroveKnowledgeBase
- **Docker container** `mangrove-sweep` with `--restart unless-stopped`
- **config_hash** column in Parquet schema (SHA256 of full strategy config for dedup)
- **Dual search mode** -- random (sample N) and grid (enumerate all)
- **GitHub repo** -- https://github.com/MangroveTechnologies/MarketSimulator

### Quick Start

```bash
cd MarketSimulator
docker compose up -d
# Dashboard at http://localhost:5100/
# CLI guide at docs/running-experiments-cli.md
```

Options:
- `docker compose down` -- stop the container
- `docker logs -f mangrove-sweep` -- tail logs

### Prerequisites

1. **MangroveAI source** at `../MangroveAI/src/MangroveAI` (mounted into container)
2. **MangroveKnowledgeBase** at `../MangroveKnowledgeBase` (pip-installed from source at startup)
3. **Docker image** `mangroveai-mangrove-app` (the MangroveAI base image)
4. **Docker network** `mangrove-network` (`docker network create mangrove-network`)
5. **GCP credentials** at `~/.config/gcloud/application_default_credentials.json`
6. **Node.js 18+** for building the React UI (optional -- built dist served if available)

### OHLCV Data Path

Both sweep workers and visualize use the same mechanism:

1. Load signal-timeframe CSV from `data/ohlcv/`
2. Load daily companion CSV (auto-generated, same directory)
3. Inject both into MangroveAI's `_OHLCV_CACHE` with keys matching the engine's exact lookup pattern
4. Engine finds cached data, never calls CoinAPI

Cache keys must match: `(provider, asset_with_USDT, interval, atr_adjusted_start_iso, end_iso)`.
The shared utility `ohlcv_utils.py` handles key computation, file loading, and injection.

The first ~14 simulated days of any sub-daily backtest are ATR warmup (no trades). This is
normal -- the daily rolling window needs 14 bars before ATR can compute.

### Known Backend Limitations

1. **config_hash stored but not checked** -- The hash is computed and written to Parquet
   per result row, but the worker does NOT check for duplicates before running. Dedup
   needs to be added to the worker loop.

2. **Exit signal validation** -- MangroveAI's Strategy class requires exit rules to have
   exactly 1 TRIGGER if any exit signals are specified. The random plan generator can
   create exit configs with only FILTER signals (no trigger), causing ValueError.

3. **Multi-filter entry limitation** -- MangroveAI's backtest engine only uses the first
   filter in entry when multiple are provided. The plan generator can create multi-filter
   entries, but only the first filter is actually evaluated. Engine limitation.

4. **win_rate stored as 0-100** -- The engine returns win_rate as a percentage (e.g., 60.0
   for 60%). Display code must NOT multiply by 100 again.

5. **Experiment status detection** -- Workers don't update experiment status to "completed"
   when done. Need auto-completion detection.

6. **All prior experiment results are stale** -- Experiments run before 2026-03-03 used
   CoinAPI/Redis data (the _OHLCV_CACHE injection was broken). Results are not
   reproducible from local files. Re-run experiments for accurate results.

### Design Documents

All in `docs/plans/`:
- `2026-02-28-experiment-framework-requirements.md`
- `2026-02-28-experiment-framework-specification.md`
- `2026-02-28-experiment-framework-architecture.md`
- `2026-02-28-experiment-framework-implementation.md`
- `2026-03-01-experiment-framework-ui-ux.md`

### CLI Guide

See `docs/running-experiments-cli.md` for full REST API usage examples.

### React Dev Workflow

```bash
cd experiment_ui
npm install
npm run dev          # Dev server on :5200 with proxy to :5100
npm run build        # Builds to ../experiment_ui_dist/ (served by FastAPI)
```

### API Docs

http://localhost:5100/docs
