# Sweep V2 -- Generalized Random Search

Design notes for the next-generation parallel backtest sweep. Builds on the
lessons and infrastructure from `run_permutation_sweep_parallel.py` (v1).

## What V1 does

- 1 trigger + 1 filter per entry
- Fixed execution_config across all runs
- Exhaustive grid: every trigger x filter pair, N param combos each
- 12 workers (2 per symbol), chunk-based CSV output, deterministic resume

## What V2 adds

### 1. Multi-filter entry

Allow 1 trigger + K filters (K >= 1) per entry configuration.

**Problem**: combinatorial explosion. 62 filters, C(62,2) = 1,891 pairs,
C(62,3) = 37,820 triples. Full enumeration is not viable.

**Approach**: sample N total entry configurations per trigger, where each config
draws K filters at random. K is controlled by `--min-filters` / `--max-filters`.

- For each trigger, draw N entry configs:
  - Sample K ~ Uniform(min_filters, max_filters)
  - Sample K filter signals without replacement
  - Sample params for each filter independently
- This keeps combo count proportional to N, not to C(62,K)

**Output schema change**:
- `filter_name` -> `filter_names` (comma-separated, ordered alphabetically for dedup)
- `filter_params` -> `filter_params_list` (JSON array, same order as filter_names)
- Add `num_filters` column for easy grouping

### 2. Execution config sweeping

V1 uses one fixed EXECUTION_CONFIG. V2 varies execution parameters.

**Candidate params to sweep**:

| Param | V1 value | Suggested candidates |
|-------|----------|---------------------|
| reward_factor | 2.0 | 1.5, 2.0, 3.0, 5.0 |
| max_risk_per_trade | 0.02 | 0.01, 0.02, 0.05 |
| max_open_positions | 10 | 1, 3, 5, 10 |
| cooldown_bars | 3 | 0, 1, 3, 5 |
| target_volatility | 0.01 | 0.005, 0.01, 0.02 |
| volatility_window | 20 | 10, 20, 40 |
| max_trades_per_day | 5 | 3, 5, 10 |
| enable_volatility_adjustment | True | True, False |

Full cross-product of all 8 = ~5,000 configs. Too many as a multiplier.

**Two modes**:

- `--exec-mode independent` (default): vary one param at a time, hold others at
  defaults. ~20 configs total. Each backtest gets one of these at random.
- `--exec-mode grid`: full cross-product of selected params. User restricts
  which params via `--exec-params reward_factor,max_risk_per_trade`.
- `--exec-mode random`: sample N random exec configs from the full space.
  Controlled by `--n-exec-configs`.

**Output schema change**:
- Add `exec_config_id` (int, maps to a config variant)
- Add `exec_config_json` (full JSON of the execution config used)

### 3. Combo budget model

V1 builds an exhaustive plan. V2 uses a budget model.

`--n-combos-per-symbol 50000` controls total work per symbol. Each combo is:
(trigger, trigger_params, [filter1, filter1_params, ...], exec_config)

The plan builder samples combos uniformly from the joint space:
1. Pick a trigger at random (uniform over trigger list)
2. Sample trigger params
3. Pick K filters at random
4. Sample params for each filter
5. Pick an exec config (from the mode-dependent pool)

Deduplication via frozen-set hashing to avoid repeats. Seed-deterministic.

### 4. CLI interface

```
python run_permutation_sweep_v2.py \
  --signals kb \
  --n-combos-per-symbol 50000 \
  --min-filters 1 \
  --max-filters 3 \
  --exec-mode independent \
  --exec-params reward_factor,max_risk_per_trade,cooldown_bars \
  --workers-per-symbol 2 \
  --seed 42 \
  --resume \
  --dry-run
```

### 5. Infrastructure (same as V1)

- Chunk-based CSV output: `sweep_results_v2/{SYMBOL}/worker_{id}_chunk_{n}.csv`
- Separate output dir from V1 (no collision)
- Same resume logic: count completed rows per worker, skip forward
- Same container setup: `mangrove-sweep` with `sleep infinity`
- Same BLAS thread pinning, logger suppression, data cache injection

## Open questions

1. **Filter interaction**: does filter order matter? If the backtest engine
   evaluates filters with AND logic (all must be True), order shouldn't matter.
   Verify this -- if so, we can sort filter names alphabetically for
   deduplication and canonical naming.

2. **Filter overlap**: some filters are near-duplicates at certain param values
   (e.g., `rsi_oversold` with threshold=50 vs `rsi_neutral`). Should we
   blacklist certain filter pairs, or just let the data speak?

3. **Exec config interaction with signal params**: if we sweep both signal
   params AND exec config, the same signal combo might look great with
   aggressive risk settings and terrible with conservative ones. Is the goal
   to find (signal_combo, exec_config) pairs jointly, or to find good signal
   combos first and then tune exec config separately? Joint is more thorough
   but more expensive.

4. **Budget allocation**: should every trigger get equal representation in the
   budget, or should some triggers get more combos? Equal is simpler and
   unbiased. Weighted could focus on triggers that V1 showed are promising.

5. **Data files**: same 6 symbols and CSVs as V1, or should we prepare
   additional data? V1 coverage: BTC (1d), ETH (4h), LINK (30m), PAXG (1h),
   DOGE (5m), SOL (5m). Missing: 15m timeframe, any longer-horizon data for
   altcoins.

6. **Notebook compatibility**: the analysis notebook should work with both V1
   and V2 output. V2 adds columns but keeps V1 columns intact. Should the
   notebook auto-detect which version it's loading, or should we have separate
   load paths?

7. **Runtime estimate**: V1 is 223K combos at ~0.7/s = ~88 hours. If V2 budget
   is 50K per symbol x 6 symbols = 300K combos, that's ~120 hours at the same
   rate. Multi-filter entries might be slightly slower (more signal evaluations
   per bar). Worth benchmarking a few 2-filter and 3-filter runs before
   committing to a full sweep.

## Additional thoughts

- **Adaptive sampling**: after an initial exploratory phase (first 10% of
  budget), analyze intermediate results and bias remaining sampling toward
  promising regions. This is Bayesian optimization territory -- probably
  overkill for V2 but worth noting for V3.

- **Exit signals**: V1 and V2 both use empty exit lists (relying on the
  engine's default exit logic -- reward_factor trailing stop). A future
  sweep could add exit signal variation, but that's another dimension of
  complexity.

- **Cross-validation**: the current sweep runs each combo on the full date
  range. A more rigorous approach would split data into train/test periods
  and only report test-period metrics. This guards against overfitting to
  the specific date range. Could be a V3 feature.

- **Pareto frontier**: instead of ranking by a single metric, identify
  strategies on the Pareto frontier of (return, drawdown, trade_count).
  The notebook could add this as a scatter plot with Pareto front highlighted.
