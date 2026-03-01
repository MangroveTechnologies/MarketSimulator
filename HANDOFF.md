# MarketSimulator -- Handoff Document

Last updated: 2026-02-27

This document captures the current state of all workstreams in MarketSimulator
so that any future session can pick up where we left off.

## Directory Structure

```
MarketSimulator/
  market_simulator.ipynb       Original agent-based market simulator (MDP, 5 agent types)
  market-simulator.md          Design doc for the simulator
  monte_carlo.ipynb            Monte Carlo analysis notebook
  scripts/
    run_permutation_sweep.py          Single-threaded backtest sweep
    run_permutation_sweep_parallel.py Parallel sweep (12 workers, 2 per symbol)
    sweep_v2_design.md                Design doc for next-gen sweep (multi-filter, exec_config)
    benchmark/
      run_benchmark.py                LLM model benchmark orchestrator
      driver.py                       Conversation driver (user agent + state machine)
      scenario_generator.py           Random scenario generation from data files
      user_agent.py                   LLM-driven user agent
      judge.py                        Multi-judge transcript scoring (7-criterion rubric)
      model_switcher.py               DB-level model switching + cache invalidation
      data_loader.py                  OHLCV data file discovery
      results.py                      Dataclasses and CSV/JSON I/O
      conversations.py                Legacy scripted scenarios (superseded by scenario_generator)
      README.md                       Full user guide for the benchmark system
      skills/
        user_agent.md                 Prompt template for user agent persona
        judge.md                      Prompt template for judge scoring rubric
  notebooks/
    sweep_analysis.ipynb              Jupyter notebook for analyzing sweep results
  data/
    sweep_results/                    Existing results from the parallel sweep
      BTC/   38 chunk files, 37,238 rows (COMPLETE)
      DOGE/   7 chunk files,  7,175 rows
      ETH/    7 chunk files,  7,175 rows
      LINK/  13 chunk files, 13,325 rows
      PAXG/  16 chunk files, 16,400 rows
      SOL/   19 chunk files, 19,475 rows
      TOTAL: 100 files, 100,788 rows (~45% of 223,200 planned)
```

## Runtime Dependencies

All scripts in this project depend on MangroveAI at runtime. They import:
- `MangroveAI.domains.backtesting` (backtest engine)
- `MangroveAI.domains.signals` (signal registry)
- `MangroveAI.domains.ai_copilot` (copilot state machine, LLM client)
- `MangroveAI.utils` (database, logging)

OHLCV data files live in MangroveAI's data directory, not here.

## Container Setup

Both projects must be mounted. The container uses MangroveAI's Docker image
(which has all Python dependencies installed).

```bash
# Create the container
docker run -d --name mangrove-sweep \
    --network mangrove-network \
    -v /path/to/MangroveAI/src/MangroveAI:/app/MangroveAI \
    -v /path/to/MarketSimulator:/app/MarketSimulator \
    -v ~/.config/gcloud/application_default_credentials.json:/tmp/keys/google_credentials.json:ro \
    -e OMP_NUM_THREADS=1 \
    -e OPENBLAS_NUM_THREADS=1 \
    -e MKL_NUM_THREADS=1 \
    -e ENVIRONMENT=local \
    -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/keys/google_credentials.json \
    -e GCP_PROJECT_ID=mangroveai-dev \
    mangroveai-mangrove-app sleep infinity

# Run sweep
docker exec -w /app/MarketSimulator/scripts mangrove-sweep \
    python run_permutation_sweep_parallel.py --resume

# Run benchmark
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --dry-run
```

The MangroveAI PostgreSQL container (`mangroveai-postgres-1`) must also be
running on `mangrove-network` for the benchmark (it reads model configs from
the database). Start it with `cd MangroveAI && docker compose up -d postgres`.

---

## Workstream 1: Backtest Permutation Sweep

### Status: ~45% complete, paused

The parallel sweep tests every (trigger x filter x params) combination across
6 symbols. Each symbol has its own timeframe and date range:

| Symbol | Timeframe | Date Range | Status |
|--------|-----------|------------|--------|
| BTC | 1d | 2022-08-01 to 2026-02-15 | COMPLETE (37,238 rows) |
| ETH | 4h | 2024-01-01 to 2026-02-01 | ~19% |
| LINK | 30m | 2025-07-04 to 2026-02-12 | ~36% |
| PAXG | 1h | 2025-01-01 to 2026-02-14 | ~44% |
| DOGE | 5m | 2021-04-01 to 2021-06-15 | ~19% |
| SOL | 5m | 2026-02-01 to 2026-02-16 | ~52% |

### To resume

```bash
docker exec -w /app/MarketSimulator/scripts mangrove-sweep \
    python run_permutation_sweep_parallel.py --resume
```

The `--resume` flag counts existing rows per worker and skips forward.
Estimated time for remaining ~122K combos: ~48 hours at ~0.7 combos/sec.

### Configuration

- 24 trigger signals x 62 filter signals from KB metadata
- 3 param combos per signal (n_trigger=3, n_filter=3)
- Fixed execution_config (see EXECUTION_CONFIG in the script)
- 12 workers (2 per symbol), chunk size = 1024 rows
- Seed = 42 (deterministic combo plans)

### Key findings so far

Run the analysis notebook (`notebooks/sweep_analysis.ipynb`) for full results.
Highlights from 100K rows:
- 27.3% of combos produce trades (72.7% are no-trade)
- Top performers: BTC daily with pvo_bearish_cross + nvi_bearish (Sharpe > 5)
- mass_reversal_signal on DOGE 5m produces highest trade counts (2900+)
- Zero errors across all 100K runs

### Next steps (sweep v2)

See `scripts/sweep_v2_design.md` for the full design. Key additions:
- Multi-filter entry (1 trigger + K filters, K=1..3)
- Execution config sweeping (reward_factor, risk, cooldown, etc.)
- Budget-based sampling instead of exhaustive grid
- Open questions about filter interaction, budget allocation

---

## Workstream 2: LLM Model Benchmark

### Status: fully coded, not yet run

The benchmark tests all eligible LLM models against MangroveAI's copilot
state machine using a 3-agent design:

1. **User agent** (gpt-4.1-nano) generates user messages following a scenario
2. **Copilot under test** processes messages through the state machine
3. **Judge agent(s)** score the transcript on 7 criteria (1-5 scale)

### To run

```bash
# Dry run first (no API calls, shows model x scenario matrix)
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --dry-run

# Single-model smoke test
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --models MiniMax-M2.5 --n-scenarios 1

# Full benchmark
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --n-scenarios 5
```

### Prerequisites

- MangroveAI postgres running (for llm_models and llm_model_configs tables)
- API keys configured for all providers (OpenAI, Anthropic, xAI, MiniMax)
- OHLCV data files in MangroveAI/data/

### Output

Results go to `data/benchmark_results/run_<timestamp>/`:
- `summary.csv` -- one row per (model, scenario)
- `judge_scores.csv` -- one row per (model, scenario, judge)
- `raw_results.json` -- full data with per-turn metrics
- `checkpoint.json` -- for resume after interruption

### Judge scoring criteria

1. Intent comprehension
2. Signal selection quality
3. Parameter reasonableness
4. Conversation quality
5. Guardrail compliance
6. Efficiency
7. Error recovery

See `scripts/benchmark/README.md` for the full user guide.

### Next steps (benchmark)

- Run the first dry-run and smoke test
- Build analysis notebook for benchmark results
- Consider weighted scoring (guardrail compliance > efficiency)
- Consider parallel execution across models
- Add cost tracking for user agent and judge LLM calls
