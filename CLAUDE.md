# MarketSimulator

Three-pillar research project under the Mangrove portfolio. Read the parent [CLAUDE.md](../CLAUDE.md) for the full project landscape.

## Three Workstreams

### 1. Agent-Based Market Simulator
- MDP framework, 5 agent types, square-root impact model
- Generates synthetic OHLCV data for BTC, XAU, META, CL
- Lives in `market_simulator.ipynb` and `market-simulator.md`
- Fully functional but not yet extracted to a Python module

### 2. Backtest Permutation Sweep
- Tests every (trigger x filter x params) combination across 6 crypto symbols
- 12 parallel workers, chunk-based CSV output, deterministic resume
- **Status**: ~45% complete (100,788 / 223,200 rows). BTC done. Paused.
- V2 designed but not built (see `scripts/sweep_v2_design.md`)
- Entry point: `scripts/run_permutation_sweep_parallel.py`

### 3. LLM Copilot Benchmark
- 3-agent design: user agent (gpt-4.1-nano), copilot under test, judge (claude-sonnet-4-6)
- Scores 7 criteria: intent, signal selection, parameters, conversation, guardrails, efficiency, error recovery
- **Status**: Fully coded, not yet run. Needs first dry-run.
- Entry point: `scripts/benchmark/run_benchmark.py`
- Full docs: `scripts/benchmark/README.md`

## Runtime Dependencies

All scripts depend on MangroveAI at runtime. They must run inside the `mangrove-sweep` Docker container with both projects mounted:

```bash
docker exec -w /app/MarketSimulator/scripts mangrove-sweep \
    python run_permutation_sweep_parallel.py --resume

docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --dry-run
```

Imports: `MangroveAI.domains.backtesting`, `MangroveAI.domains.signals`, `MangroveAI.domains.ai_copilot`, `MangroveAI.utils`. OHLCV data lives in `MangroveAI/data/`, not here.

## Key Conventions

- **No package structure yet** — scripts use `sys.path.insert(0, "/app")` to find MangroveAI
- **BLAS thread pinning** — always set OMP/OPENBLAS/MKL_NUM_THREADS=1 in container env
- **Chunk-based output** — sweep writes 1024-row CSV chunks per worker, not one big file
- **Seed determinism** — use `--seed 42` for reproducible combo plans and scenarios
- **Logger suppression** — backtesting/strategies/managers/positions loggers set to WARNING
- **stdout suppression** — backtest engine print() redirected to /dev/null during sweep

## File Map

| Path | Purpose |
|------|---------|
| `HANDOFF.md` | Detailed status of every workstream with resume instructions |
| `market_simulator.ipynb` | Original agent-based simulator (MDP, 5 types, impact model) |
| `market-simulator.md` | Simulator design doc |
| `monte_carlo.ipynb` | Monte Carlo strategy research |
| `scripts/run_permutation_sweep.py` | Single-threaded sweep (exports shared infra) |
| `scripts/run_permutation_sweep_parallel.py` | 12-worker parallel sweep |
| `scripts/sweep_v2_design.md` | V2 design: multi-filter, exec config, budget model |
| `scripts/benchmark/` | Full LLM benchmark system (9 modules + 2 skill prompts) |
| `notebooks/sweep_analysis.ipynb` | Sweep results analysis |
| `data/sweep_results/` | ~100K rows across BTC, ETH, LINK, PAXG, DOGE, SOL |

## What NOT to Do

- Don't modify sweep result CSVs in `data/sweep_results/` — they are append-only output
- Don't hardcode container paths outside of scripts (they use `/app/` prefix)
- Don't call CoinAPI — all data is loaded from local CSVs via cache injection
- Don't change `EXECUTION_CONFIG` in the sweep scripts without documenting why (it affects all results)
- Don't run the benchmark without MangroveAI postgres running (`docker compose up -d postgres`)
