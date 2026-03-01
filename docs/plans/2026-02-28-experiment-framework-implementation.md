# Experiment Framework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone FastAPI + React experimentation dashboard for configuring, launching, monitoring, and analyzing backtest sweep experiments at scale.

**Architecture:** FastAPI backend (DuckDB + Parquet for results, Redis for job queue + progress + trade cache), React 18 frontend (Vite + Tailwind). Workers import MangroveAI's backtest engine at runtime. See `docs/plans/2026-02-28-experiment-framework-architecture.md` for full architecture.

**Tech Stack:** Python 3.12, FastAPI, DuckDB, PyArrow, Redis, RQ, Pydantic | React 18, Vite, Tailwind CSS, Axios, lightweight-charts

**Design docs (read these first):**
- `docs/plans/2026-02-28-experiment-framework-requirements.md`
- `docs/plans/2026-02-28-experiment-framework-specification.md`
- `docs/plans/2026-02-28-experiment-framework-architecture.md`
- `docs/data-model-exploration.md`

---

## Phase 1: Backend Core (data layer + services)

### Task 1: Project scaffold and Pydantic models

**Files:**
- Create: `experiment_server/__init__.py`
- Create: `experiment_server/config.py`
- Create: `experiment_server/models/__init__.py`
- Create: `experiment_server/models/experiment.py`
- Create: `experiment_server/models/results.py`

**Step 1: Create config module**

```python
# experiment_server/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379"
    data_dir: str = "/app/MarketSimulator/data"
    mangrove_data_dir: str = "/app/MangroveAI/data"
    signals_metadata_path: str = "/app/MangroveAI/domains/signals/signals_metadata.json"
    trading_defaults_path: str = "/app/MangroveAI/domains/ai_copilot/prompts/trading_defaults.json"
    chunk_size: int = 1024
    api_port: int = 5100

    class Config:
        env_prefix = "EXP_"

settings = Settings()
```

**Step 2: Create Pydantic models**

Create the full set of models from the specification document section 6 (ParamSweep, SignalConfig, SignalSelection, ExecConfigSweep, DatasetSelection, ExperimentConfig, ResultRow, ProgressEvent). Every field, every type, every default -- reference the spec exactly.

**Step 3: Create `__init__.py`**

```python
# experiment_server/__init__.py
"""Experiment Framework for MarketSimulator."""
```

**Step 4: Verify imports work**

Run: `cd /app/MarketSimulator && python -c "from experiment_server.models.experiment import ExperimentConfig; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add experiment_server/
git commit -m "feat: experiment framework scaffold with Pydantic models"
```

---

### Task 2: Parquet writer (PyArrow schema + chunk writer)

**Files:**
- Create: `experiment_server/workers/__init__.py`
- Create: `experiment_server/workers/parquet_writer.py`
- Create: `tests/test_parquet_writer.py`

**Step 1: Write the failing test**

```python
# tests/test_parquet_writer.py
import os
import tempfile
import duckdb
from experiment_server.workers.parquet_writer import ParquetChunkWriter, RESULT_SCHEMA

def test_write_and_read_single_chunk():
    with tempfile.TemporaryDirectory() as tmpdir:
        writer = ParquetChunkWriter(
            output_dir=tmpdir,
            worker_id=0,
            chunk_size=3,
            experiment_config={"experiment_id": "test_exp", "name": "test"},
        )
        for i in range(3):
            writer.add_row(_make_test_row(i))
        writer.flush()
        writer.close()

        # Verify file exists
        files = [f for f in os.listdir(tmpdir) if f.endswith(".parquet")]
        assert len(files) == 1
        assert files[0] == "worker_00_chunk_000.parquet"

        # Verify data via DuckDB
        conn = duckdb.connect()
        df = conn.execute(f"SELECT * FROM read_parquet('{tmpdir}/*.parquet')").fetchdf()
        assert len(df) == 3
        assert list(df["run_index"]) == [0, 1, 2]
        assert df["experiment_id"].iloc[0] == "test_exp"
        conn.close()

def _make_test_row(run_index: int) -> dict:
    return {
        "experiment_id": "test_exp",
        "run_index": run_index,
        "code_version": "abc123",
        "rng_seed": 42,
        "data_file_path": "test.csv",
        "data_file_hash": "sha256:abc",
        "data_file_rows": 100,
        "strategy_name": "test_strategy",
        "asset": "BTC",
        "timeframe": "1d",
        "start_date": "2022-08-01",
        "end_date": "2026-02-15",
        "entry_json": '[{"name":"ema_cross_up","signal_type":"TRIGGER","timeframe":"1d","params":{"window_fast":9,"window_slow":21}}]',
        "trigger_name": "ema_cross_up",
        "num_entry_signals": 1,
        "exit_json": "[]",
        "num_exit_signals": 0,
        "reward_factor": 2.0,
        "max_risk_per_trade": 0.01,
        "stop_loss_calculation": "dynamic_atr",
        "atr_period": 14,
        "atr_volatility_factor": 2.0,
        "atr_short_weight": 0.7,
        "atr_long_weight": 0.3,
        "initial_balance": 10000.0,
        "min_balance_threshold": 0.1,
        "min_trade_amount": 25.0,
        "max_open_positions": 1,
        "max_trades_per_day": 5,
        "max_units_per_trade": 10000.0,
        "max_trade_amount": 10000000.0,
        "volatility_window": 24,
        "target_volatility": 0.02,
        "volatility_mode": "stddev",
        "enable_volatility_adj": False,
        "max_hold_time_hours": None,
        "cooldown_bars": 2,
        "daily_momentum_limit": 3.0,
        "weekly_momentum_limit": 3.0,
        "max_hold_bars": 100,
        "exit_on_loss_after_bars": 50,
        "exit_on_profit_after_bars": 100,
        "profit_threshold_pct": 0.04,
        "slippage_pct": 0.0075,
        "fee_pct": 0.0085,
        "total_trades": 10,
        "win_rate": 0.6,
        "total_return": 15.5,
        "sharpe_ratio": 1.8,
        "sortino_ratio": 2.1,
        "max_drawdown": 5.2,
        "max_drawdown_duration": 12,
        "calmar_ratio": 3.0,
        "gain_to_pain_ratio": 2.5,
        "irr_annualized": 12.0,
        "irr_daily": 0.03,
        "avg_daily_return": 0.04,
        "max_consecutive_wins": 5,
        "max_consecutive_losses": 2,
        "num_days": 365,
        "net_pnl": 1550.0,
        "starting_balance_result": 10000.0,
        "ending_balance": 11550.0,
        "status": "ok",
        "error_msg": None,
        "elapsed_seconds": 3.5,
        "completed_at": "2026-02-28T14:30:00Z",
    }
```

**Step 2: Run test to verify it fails**

Run: `cd /app/MarketSimulator && python -m pytest tests/test_parquet_writer.py -v`
Expected: FAIL (module not found)

**Step 3: Implement ParquetChunkWriter**

Implement in `experiment_server/workers/parquet_writer.py`. Define `RESULT_SCHEMA` as a `pa.schema()` with all 67 columns from the spec (section 1.1). The writer:
- Accepts rows via `add_row(row_dict)`
- Buffers in a list
- Flushes to `worker_{nn}_chunk_{nnn}.parquet` when buffer reaches `chunk_size`
- Embeds experiment config in Parquet file metadata via `schema.with_metadata()`
- `close()` flushes any remaining buffer

**Step 4: Run test to verify it passes**

Run: `cd /app/MarketSimulator && python -m pytest tests/test_parquet_writer.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add experiment_server/workers/ tests/test_parquet_writer.py
git commit -m "feat: Parquet chunk writer with full 67-column schema"
```

---

### Task 3: Dataset discovery service

**Files:**
- Create: `experiment_server/services/__init__.py`
- Create: `experiment_server/services/dataset.py`
- Create: `tests/test_dataset_service.py`

**Step 1: Write the failing test**

```python
# tests/test_dataset_service.py
import os
import tempfile
import hashlib
from experiment_server.services.dataset import discover_datasets, compute_file_hash

def test_discover_datasets_finds_matching_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test CSV matching the naming convention
        path = os.path.join(tmpdir, "btc_2022-08-01_2026-02-15_1d.csv")
        with open(path, "w") as f:
            f.write("timestamp,open,high,low,close,volume\n")
            f.write("2022-08-01,23000,24000,22000,23500,1000\n")

        datasets = discover_datasets(tmpdir)
        assert len(datasets) == 1
        assert datasets[0].asset == "BTC"
        assert datasets[0].timeframe == "1d"
        assert datasets[0].rows == 1

def test_compute_file_hash_deterministic():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("test data\n")
        path = f.name
    h1 = compute_file_hash(path)
    h2 = compute_file_hash(path)
    assert h1 == h2
    assert h1.startswith("sha256:")
    os.unlink(path)
```

**Step 2: Run test to verify it fails**

Run: `cd /app/MarketSimulator && python -m pytest tests/test_dataset_service.py -v`
Expected: FAIL

**Step 3: Implement dataset service**

Reuse the file discovery logic from `scripts/benchmark/data_loader.py` (regex pattern, valid timeframes). Add `compute_file_hash()` using SHA256. Return `DatasetSelection` Pydantic models.

**Step 4: Run test to verify it passes**

Run: `cd /app/MarketSimulator && python -m pytest tests/test_dataset_service.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add experiment_server/services/ tests/test_dataset_service.py
git commit -m "feat: dataset discovery service with file hashing"
```

---

### Task 4: Signal metadata service

**Files:**
- Create: `experiment_server/services/signal.py`
- Create: `tests/test_signal_service.py`

**Step 1: Write the failing test**

```python
# tests/test_signal_service.py
import json
import tempfile
import os
from experiment_server.services.signal import load_signals

def test_load_signals_from_metadata():
    metadata = {
        "ema_cross_up": {
            "type": "TRIGGER",
            "params": {
                "window_fast": {"type": "int", "min": 5, "max": 30, "default": 9},
                "window_slow": {"type": "int", "min": 20, "max": 100, "default": 21}
            },
            "constraints": [["window_fast", "<", "window_slow"]]
        },
        "rsi_oversold": {
            "type": "FILTER",
            "params": {
                "window": {"type": "int", "min": 7, "max": 28, "default": 14},
                "threshold": {"type": "float", "min": 20, "max": 40, "default": 30}
            },
            "constraints": []
        }
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(metadata, f)
        path = f.name

    signals = load_signals(path)
    assert len(signals) == 2
    triggers = [s for s in signals if s["type"] == "TRIGGER"]
    filters = [s for s in signals if s["type"] == "FILTER"]
    assert len(triggers) == 1
    assert len(filters) == 1
    assert triggers[0]["name"] == "ema_cross_up"
    assert triggers[0]["params"]["window_fast"]["min"] == 5
    os.unlink(path)
```

**Step 2: Run test, implement, run test, commit**

Same pattern. Load signals from `signals_metadata.json`, return structured dicts with name, type, params (with min/max/default/type), and constraints.

**Step 5: Commit**

```bash
git add experiment_server/services/signal.py tests/test_signal_service.py
git commit -m "feat: signal metadata service loading from KB"
```

---

### Task 5: Plan generator (grid search + random search + constraints)

**Files:**
- Create: `experiment_server/services/plan_generator.py`
- Create: `tests/test_plan_generator.py`

This is the most complex service. It takes an `ExperimentConfig` and produces a deterministic list of run specifications.

**Step 1: Write failing tests**

```python
# tests/test_plan_generator.py
from experiment_server.services.plan_generator import generate_plan
from experiment_server.models.experiment import ExperimentConfig

def test_grid_search_generates_all_combinations():
    config = _make_simple_config(search_mode="grid")
    plan = generate_plan(config)
    # 1 trigger x 2 trigger_params x 1 filter x 2 filter_params x 1 dataset = 4 runs
    assert len(plan) == 4
    # All run_index values unique and sequential
    assert [r.run_index for r in plan] == [0, 1, 2, 3]

def test_random_search_respects_n():
    config = _make_simple_config(search_mode="random", n_random=2)
    plan = generate_plan(config)
    assert len(plan) == 2

def test_same_seed_produces_same_plan():
    config = _make_simple_config(search_mode="random", n_random=10)
    plan1 = generate_plan(config)
    plan2 = generate_plan(config)
    assert [r.run_index for r in plan1] == [r.run_index for r in plan2]

def test_constraints_filter_invalid_combos():
    config = _make_config_with_constraints()
    plan = generate_plan(config)
    for run in plan:
        entry = json.loads(run.entry_json)
        trigger = entry[0]
        assert trigger["params"]["window_fast"] < trigger["params"]["window_slow"]

def _make_simple_config(**overrides):
    # Build a minimal ExperimentConfig with known param values
    ...
```

**Step 2: Run test to verify failure**

**Step 3: Implement plan generator**

Key functions:
- `expand_param_sweep(param_sweep: ParamSweep) -> list[value]` -- expand min/max/step or explicit values
- `generate_signal_param_combos(signal: SignalConfig) -> list[dict]` -- cartesian product of all param values
- `apply_constraints(combos: list, constraints: list) -> list` -- filter invalid combos
- `generate_exec_config_variants(exec_config: ExecConfigSweep) -> list[dict]` -- expand sweep axes
- `generate_plan(config: ExperimentConfig) -> list[RunSpec]` -- compose everything

Each `RunSpec` is a dataclass with: `run_index`, `dataset_key`, `entry_json`, `exit_json`, `trigger_name`, `num_entry_signals`, `num_exit_signals`, and all 28 exec config field values.

**Step 4: Run test, verify pass**

**Step 5: Commit**

```bash
git add experiment_server/services/plan_generator.py tests/test_plan_generator.py
git commit -m "feat: deterministic plan generator with grid/random search and constraints"
```

---

### Task 6: DuckDB query service

**Files:**
- Create: `experiment_server/services/query.py`
- Create: `tests/test_query_service.py`

**Step 1: Write failing test**

```python
# tests/test_query_service.py
import tempfile
from experiment_server.workers.parquet_writer import ParquetChunkWriter
from experiment_server.services.query import query_results, count_completed

def test_query_results_with_filters():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=20)
        results = query_results(
            experiment_dir=tmpdir,
            filters={"asset": "BTC", "status": "ok"},
            sort="sharpe_ratio",
            order="desc",
            limit=5,
            offset=0,
        )
        assert len(results["results"]) <= 5
        # Verify sorting
        sharpes = [r["sharpe_ratio"] for r in results["results"]]
        assert sharpes == sorted(sharpes, reverse=True)

def test_count_completed_returns_run_indices():
    with tempfile.TemporaryDirectory() as tmpdir:
        _write_test_data(tmpdir, n=10)
        completed = count_completed(tmpdir)
        assert len(completed) == 10
        assert 0 in completed
        assert 9 in completed
```

**Step 2-5: Implement, test, commit**

The query service wraps DuckDB with parameterized SQL. Uses `read_parquet()` with glob patterns. Handles pagination via `LIMIT/OFFSET` and count via a separate query.

```bash
git commit -m "feat: DuckDB query service for Parquet results"
```

---

### Task 7: Strategy config reconstruction

**Files:**
- Create: `experiment_server/services/reconstruct.py`
- Create: `tests/test_reconstruct.py`

**Step 1: Write failing test**

Test that `reconstruct_strategy_config(row_dict)` produces a valid strategy config JSON that matches the original input. Round-trip test: build a config, flatten to row, reconstruct, compare.

**Step 2-5: Implement, test, commit**

```bash
git commit -m "feat: strategy config reconstruction from Parquet row"
```

---

## Phase 2: Worker and executor

### Task 8: Sweep worker (RQ job function)

**Files:**
- Create: `experiment_server/workers/sweep_worker.py`
- Create: `tests/test_sweep_worker.py`

The worker function that RQ calls. It:
1. Loads the experiment config from `config.json`
2. Loads the OHLCV DataFrame for its assigned dataset
3. Queries completed run_indices from existing Parquet files
4. For each assigned run_index: set RNG seed, build strategy config, call `run_single_backtest()`, buffer result row, publish progress to Redis Stream
5. Flushes Parquet chunks at `chunk_size` intervals

**Step 1: Write test**

Test with a mock backtest engine (patch `run_single_backtest` to return fake results). Verify Parquet output and Redis progress publishing.

**Step 2-5: Implement, test, commit**

```bash
git commit -m "feat: sweep worker with Parquet output and Redis progress"
```

---

### Task 9: Executor service (launch/pause/resume)

**Files:**
- Create: `experiment_server/services/executor.py`
- Create: `tests/test_executor.py`

Manages experiment lifecycle:
- `launch(experiment_id)`: generate plan, split across workers, enqueue RQ jobs
- `pause(experiment_id)`: signal workers to stop via Redis key
- `resume(experiment_id)`: query completed indices, re-enqueue remaining work
- `get_status(experiment_id)`: check Redis for worker status

**Step 1: Write test**

Test with a mocked Redis and mocked RQ queue. Verify jobs are enqueued with correct payloads.

**Step 2-5: Implement, test, commit**

```bash
git commit -m "feat: executor service for experiment launch/pause/resume"
```

---

## Phase 3: FastAPI routes

### Task 10: FastAPI app factory and experiment CRUD

**Files:**
- Create: `experiment_server/app.py`
- Create: `experiment_server/routes/__init__.py`
- Create: `experiment_server/routes/experiments.py`
- Create: `tests/test_api_experiments.py`

**Step 1: Write failing test**

```python
# tests/test_api_experiments.py
from fastapi.testclient import TestClient
from experiment_server.app import create_app

client = TestClient(create_app())

def test_create_experiment():
    resp = client.post("/api/v1/experiments", json=_valid_config())
    assert resp.status_code == 201
    assert "experiment_id" in resp.json()

def test_list_experiments():
    resp = client.get("/api/v1/experiments")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

**Step 2-5: Implement CRUD routes, test, commit**

```bash
git commit -m "feat: FastAPI app with experiment CRUD endpoints"
```

---

### Task 11: Dataset and signal routes

**Files:**
- Create: `experiment_server/routes/datasets.py`
- Create: `experiment_server/routes/signals.py`

Wire the dataset and signal services to GET endpoints. Straightforward -- the services already exist.

```bash
git commit -m "feat: dataset and signal listing API endpoints"
```

---

### Task 12: Results query route

**Files:**
- Create: `experiment_server/routes/results.py`

Wire the DuckDB query service to `GET /api/v1/experiments/{id}/results` with all filter/sort/pagination params from the spec.

```bash
git commit -m "feat: results query endpoint with DuckDB"
```

---

### Task 13: Lifecycle routes (validate, launch, pause, resume)

**Files:**
- Modify: `experiment_server/routes/experiments.py`

Add `POST /validate`, `POST /launch`, `POST /pause`, `POST /resume` endpoints. Wire to the executor and plan generator services.

```bash
git commit -m "feat: experiment lifecycle endpoints (validate, launch, pause, resume)"
```

---

### Task 14: SSE progress endpoint

**Files:**
- Create: `experiment_server/routes/progress.py`

Implement `GET /api/v1/experiments/{id}/progress` as an SSE stream reading from Redis Streams. Use `StreamingResponse` from FastAPI.

```bash
git commit -m "feat: SSE progress streaming endpoint"
```

---

### Task 15: Visualization endpoint (on-demand backtest re-run)

**Files:**
- Modify: `experiment_server/routes/results.py`

Add `GET /api/v1/experiments/{id}/results/{run_index}/visualize`. Reconstructs the strategy config from the result row, calls `run_single_backtest()`, caches trades in Redis with 1-hour TTL, returns metrics + trades.

```bash
git commit -m "feat: on-demand backtest visualization with Redis trade cache"
```

---

### Task 16: Template routes

**Files:**
- Create: `experiment_server/routes/templates.py`

CRUD for templates stored as JSON files in `data/templates/`.

```bash
git commit -m "feat: template save/load/delete endpoints"
```

---

### Task 17: Integration test -- end-to-end API

**Files:**
- Create: `tests/test_integration.py`

Full flow: create experiment -> validate -> launch (mocked workers) -> query results -> visualize a run. Tests the API contracts match the spec.

```bash
git commit -m "test: end-to-end API integration test"
```

---

## Phase 4: React frontend

### Task 18: Scaffold React app

**Files:**
- Create: `experiment_ui/` (Vite + React 18 + Tailwind + React Router)

```bash
cd /app/MarketSimulator
npm create vite@latest experiment_ui -- --template react
cd experiment_ui
npm install react-router-dom axios @heroicons/react/24/outline lightweight-charts
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```

Configure Tailwind, add proxy to FastAPI in `vite.config.js`, set up React Router with three routes (/configure, /monitor, /explore).

```bash
git commit -m "feat: React frontend scaffold with routing"
```

---

### Task 19: Common components (CollapsibleSection, StatusBadge, ProgressBar)

**Files:**
- Create: `experiment_ui/src/components/common/CollapsibleSection.jsx`
- Create: `experiment_ui/src/components/common/StatusBadge.jsx`
- Create: `experiment_ui/src/components/common/ProgressBar.jsx`

Follow MangroveAI admin patterns: `bg-gray-50` headers, chevron icons, `transition-colors`, semantic status colors.

```bash
git commit -m "feat: common UI components (CollapsibleSection, StatusBadge, ProgressBar)"
```

---

### Task 20: Configure View -- DatasetSelector

**Files:**
- Create: `experiment_ui/src/components/datasets/DatasetSelector.jsx`

Multi-select table with search, sort, checkboxes. Calls `GET /api/v1/datasets`.

```bash
git commit -m "feat: DatasetSelector component"
```

---

### Task 21: Configure View -- SignalSelector + ParamGridBuilder

**Files:**
- Create: `experiment_ui/src/components/signals/SignalSelector.jsx`
- Create: `experiment_ui/src/components/signals/ParamGridBuilder.jsx`

Two-panel signal picker (available | selected). Each selected signal expands to show ParamGridBuilder. ParamGridBuilder adapts to data type (int/float/bool/str). Calls `GET /api/v1/signals`.

```bash
git commit -m "feat: SignalSelector and ParamGridBuilder components"
```

---

### Task 22: Configure View -- ExecConfigEditor

**Files:**
- Create: `experiment_ui/src/components/execution/ExecConfigEditor.jsx`

Table of all 28 exec config fields with sweep toggles. Calls `GET /api/v1/exec-config/defaults`. Reuses ParamGridBuilder for swept fields.

```bash
git commit -m "feat: ExecConfigEditor component"
```

---

### Task 23: Configure View -- full assembly

**Files:**
- Create: `experiment_ui/src/views/ConfigureView.jsx`

Assembles all sections (name/desc, datasets, entry signals, exit signals, exec config, search mode, provenance, actions) into a single scrollable page with CollapsibleSections. Validate and Launch buttons.

```bash
git commit -m "feat: ConfigureView with all collapsible sections"
```

---

### Task 24: Monitor View

**Files:**
- Create: `experiment_ui/src/views/MonitorView.jsx`

Experiment list with status badges. When an experiment is selected, shows progress bars (overall + per-dataset) via SSE connection. Pause/Cancel/Resume buttons.

```bash
git commit -m "feat: MonitorView with SSE progress streaming"
```

---

### Task 25: Explore View -- results table + filters

**Files:**
- Create: `experiment_ui/src/components/results/ResultsTable.jsx`
- Create: `experiment_ui/src/views/ExploreView.jsx`

Experiment selector, filter bar, paginated sortable results table. Calls `GET /api/v1/experiments/{id}/results` with query params.

```bash
git commit -m "feat: ExploreView with filterable results table"
```

---

### Task 26: Explore View -- backtest detail (metrics + chart + trades)

**Files:**
- Create: `experiment_ui/src/components/results/BacktestDetail.jsx`
- Create: `experiment_ui/src/components/results/ChartView.jsx`
- Create: `experiment_ui/src/components/results/TradesTable.jsx`

Click a row to open the detail panel. Metrics summary card, tabbed Chart/Trades. Chart uses `lightweight-charts` for OHLCV candlesticks with trade markers. Trades table shows entry/exit/P&L/exit_reason. Calls `GET .../visualize`.

```bash
git commit -m "feat: BacktestDetail with chart and trades visualization"
```

---

## Phase 5: Integration and deployment

### Task 27: Docker setup

**Files:**
- Create: `docker-compose.experiment.yml`
- Create: `supervisord.conf`

Docker compose file for the experiment framework: Redis container + experiment app container (FastAPI + Vite + RQ workers). Volume mounts for MangroveAI and MarketSimulator.

```bash
git commit -m "feat: Docker compose for experiment framework"
```

---

### Task 28: End-to-end smoke test

Run the full flow inside Docker:
1. Start containers
2. Open dashboard at `localhost:5200`
3. Configure a small experiment (1 dataset, 2 signals, grid search)
4. Validate (check run count)
5. Launch
6. Monitor progress
7. Explore results
8. Visualize a single backtest

Document any issues and fix them.

```bash
git commit -m "test: end-to-end smoke test passed"
```

---

### Task 29: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `HANDOFF.md`
- Create: `experiment_server/README.md`

Update project docs to reflect the new framework. Add startup instructions, API reference link (FastAPI auto-docs at `/docs`), and development workflow.

```bash
git commit -m "docs: update project docs for experiment framework"
```

---

## Task dependency graph

```
Task 1 (scaffold + models)
  |
  +-- Task 2 (Parquet writer)
  |     |
  +-- Task 3 (dataset service)
  |     |
  +-- Task 4 (signal service)
  |     |
  +-- Task 5 (plan generator) -- depends on 3, 4
  |     |
  +-- Task 6 (query service) -- depends on 2
  |     |
  +-- Task 7 (reconstruct) -- depends on 2
        |
  Task 8 (sweep worker) -- depends on 2, 5, 7
  Task 9 (executor) -- depends on 5, 8
        |
  Tasks 10-16 (API routes) -- depends on 3-9
  Task 17 (integration test) -- depends on 10-16
        |
  Tasks 18-26 (React frontend) -- depends on 10-16
        |
  Tasks 27-29 (deployment + docs) -- depends on all
```

Phase 1 tasks (1-7) are mostly independent and can be parallelized.
Phase 2 tasks (8-9) depend on Phase 1.
Phase 3 tasks (10-17) depend on Phase 2.
Phase 4 tasks (18-26) depend on Phase 3 API being functional.
Phase 5 tasks (27-29) depend on everything.
