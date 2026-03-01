# LLM Model Benchmark for MangroveAI Copilot

Automated benchmarking system that tests all eligible LLM models against the
MangroveAI AI copilot state machine. Measures time, cost, token usage, tool
calls, and qualitative conversation quality via judge scoring.

## Table of Contents

- [Architecture](#architecture)
- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [CLI Reference](#cli-reference)
- [Output Files](#output-files)
- [Scenario Generation](#scenario-generation)
- [Judge Scoring](#judge-scoring)
- [Resume and Checkpointing](#resume-and-checkpointing)
- [Module Reference](#module-reference)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Future Work](#future-work)

---

## Architecture

```
+-------------------+       +-------------------+       +-------------------+
|  run_benchmark.py |------>|    driver.py      |------>| Copilot State     |
|  (orchestrator)   |       | (conversation     |       | Machine           |
|                   |       |  driver)           |       | (collect -> plan  |
|  - model loop     |       |                   |       |  -> assemble ->   |
|  - scenario loop  |       |  +-------------+  |       |  backtest -> done)|
|  - judge loop     |       |  | user_agent  |  |       +-------------------+
|  - checkpoint     |       |  | (LLM)       |  |
|  - CSV/JSON out   |       |  +-------------+  |
+-------------------+       +-------------------+
        |
        v
+-------------------+       +-------------------+       +-------------------+
|    judge.py       |       | scenario_generator|       |  model_switcher   |
|  (score           |       |  (random scenario |       |  (DB model swap   |
|   transcripts)    |       |   generation)     |       |   + cache flush)  |
+-------------------+       +-------------------+       +-------------------+
        |                           |
        v                           v
+-------------------+       +-------------------+
| skills/judge.md   |       |  data_loader.py   |
| (scoring rubric)  |       |  (CSV file        |
+-------------------+       |   discovery)      |
                            +-------------------+
```

### Three-Agent Design

1. **User Agent** (cheap LLM, e.g. gpt-4.1-nano): Simulates a human user
   following a scenario goal. Generates natural user messages based on
   knowledge level and conversation history.

2. **Copilot Under Test** (the model being benchmarked): Processes each user
   message through the MangroveAI state machine
   (`collect_user_input -> plan_signals -> assemble_strategy -> backtest -> done`).

3. **Judge Agent(s)** (one or more strong models): Scores the completed
   conversation transcript against a 7-criterion rubric. Optionally includes
   self-judging (the benchmarked model scores its own output).

---

## How It Works

1. **Discover models**: Query the `llm_models` DB table for all eligible
   models, filtering out Responses API models, embedding models, and other
   incompatible entries.

2. **Generate scenarios**: Sample random (asset, timeframe, strategy_type,
   knowledge_level) combinations from available data files. Each scenario
   produces a natural language goal string.

3. **For each (model, scenario) pair**:
   a. Switch `copilot_main` in the database and invalidate the config cache.
   b. The user agent LLM generates the first message based on the scenario.
   c. Feed the message to the copilot state machine and capture metrics.
   d. Repeat until the copilot reaches `done`, errors out, gets stuck, or
      hits `max_turns`.
   e. Judge model(s) score the full transcript.
   f. Save checkpoint after each conversation.

4. **Output**: Raw JSON, summary CSV, and judge scores CSV.

---

## Prerequisites

- MangroveAI Docker containers running (`docker compose up -d`)
- PostgreSQL with the `llm_models` and `llm_model_configs` tables populated
- OHLCV data files in `/app/MangroveAI/data/` matching the naming convention:
  `{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv`
- API keys configured for all providers you want to benchmark (OpenAI,
  Anthropic, xAI, MiniMax)

---

## Quick Start

### 1. Dry Run (inspect models and scenarios, no API calls)

```bash
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --dry-run
```

This prints the model x scenario matrix: how many models, how many scenarios,
pricing info, and the full scenario list with assets, timeframes, and goals.

### 2. Single-Model Smoke Test

```bash
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py \
    --models MiniMax-M2.5 --n-scenarios 1
```

Runs one scenario against one model. Good for verifying the system works
end-to-end before committing to a full run.

### 3. Two-Model Comparison

```bash
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py \
    --models MiniMax-M2.5,gpt-4.1-mini --n-scenarios 3
```

### 4. Full Benchmark (all eligible models)

```bash
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py \
    --n-scenarios 5 --seed 42
```

### 5. Custom Judges

```bash
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py \
    --judges claude-sonnet-4-6-20260217,gpt-4.1 --no-self-judge
```

---

## CLI Reference

```
usage: run_benchmark.py [OPTIONS]

Options:
  --models MODEL1,MODEL2     Comma-separated model IDs to benchmark.
                              Default: all eligible models from the DB.

  --n-scenarios N             Number of random scenarios to generate.
                              Default: 3.

  --seed SEED                 Random seed for scenario generation.
                              Default: 42. Same seed = same scenarios.

  --assets BTC,ETH            Restrict scenarios to these asset symbols.

  --judges MODEL1,MODEL2      Judge model IDs in litellm format
                              (e.g., anthropic/claude-sonnet-4-6-20260217).
                              Default: anthropic/claude-sonnet-4-6.

  --no-self-judge             Disable the benchmarked model judging its
                              own output.

  --user-agent-model MODEL    litellm model for the user agent.
                              Default: openai/gpt-4.1-nano.

  --max-turns N               Max conversation turns per scenario.
                              Default: 20.

  --timeout SECS              Per-turn timeout in seconds.
                              Default: 180.

  --delay SECS                Seconds to wait between model switches.
                              Default: 5.

  --include-pro               Include expensive pro-tier models
                              (gpt-5.2-pro, gpt-5-pro).

  --include-previous-gen      Include previous-generation Anthropic models
                              (claude-opus-4-5, claude-sonnet-4-5).

  --resume                    Resume from latest run's checkpoint.

  --output DIR                Output directory override.
                              Default: /app/MarketSimulator/data/benchmark_results/run_<timestamp>

  --dry-run                   Print model x scenario matrix without
                              executing anything.
```

---

## Output Files

Each run creates a timestamped directory under
`/app/MarketSimulator/data/benchmark_results/`:

```
run_20260226T143000Z/
  raw_results.json       Full benchmark data (all turns, all scores)
  summary.csv            One row per (model, scenario) with key metrics
  judge_scores.csv       One row per (model, scenario, judge) with scores
  checkpoint.json        Resume state (completed pairs + original model)
```

### summary.csv columns

| Column | Description |
|--------|-------------|
| model | Model ID (e.g., `gpt-4.1-mini`) |
| provider | Provider ID (e.g., `openai`) |
| scenario_id | Scenario identifier (e.g., `s_0000`) |
| asset | Asset symbol (e.g., `BTC`) |
| timeframe | Timeframe (e.g., `1d`, `4h`) |
| strategy_type | Strategy category (e.g., `momentum`) |
| knowledge_level | User persona (beginner/intermediate/advanced) |
| wall_clock_ms | Total elapsed time in milliseconds |
| input_tokens | Total input tokens consumed |
| output_tokens | Total output tokens generated |
| cost_usd | Estimated cost in USD |
| turns | Number of conversation turns |
| final_state | Terminal copilot state |
| reached_done | Whether the copilot reached the `done` state |
| strategy_ok | Whether a strategy config was produced |
| backtest_ok | Whether the backtest succeeded |
| tool_calls | Total number of tool calls made |
| error | Error message if the conversation failed |

### judge_scores.csv columns

| Column | Description |
|--------|-------------|
| model | Benchmarked model ID |
| judge_model | Judge model ID (litellm format) |
| is_self_judge | Whether the model judged its own output |
| intent_comprehension | Score 1-5: Did the copilot understand the user? |
| signal_selection_quality | Score 1-5: Were signals appropriate? |
| parameter_reasonableness | Score 1-5: Were parameters sensible? |
| conversation_quality | Score 1-5: Was the conversation natural? |
| guardrail_compliance | Score 1-5: Did the copilot follow rules? |
| efficiency | Score 1-5: Was the task completed efficiently? |
| error_recovery | Score 1-5: How well were errors handled? |
| composite_score | Unweighted mean of all 7 criteria |
| summary | Qualitative summary from the judge |

### raw_results.json structure

```
BenchmarkRun
  run_id: str
  benchmark_version: "2.0"
  user_agent_model: str
  judge_models: [str]
  copilot_meta_model: str
  embedding_model: str
  n_scenarios: int
  seed: int
  started_at: ISO 8601
  completed_at: ISO 8601
  results: [ModelResult]
    model_id: str
    provider: str
    litellm_string: str
    cost_input_per_mtok: float
    cost_output_per_mtok: float
    conversations: [ConversationResult]
      scenario_id, scenario_goal, asset, timeframe, ...
      turns: [TurnResult]
        turn_index, user_message, state_before, state_after,
        wall_clock_ms, input_tokens, output_tokens,
        tools_used, assistant_response_preview, error
      judge_scores: [JudgeScore]
        judge_model, is_self_judge, scores (7 criteria),
        composite_score, summary, strengths, weaknesses
```

---

## Scenario Generation

Scenarios are generated randomly from a pool of available (asset, timeframe)
pairs discovered by scanning OHLCV data files.

### Data File Discovery

The `data_loader` module scans `/app/MangroveAI/data/` for CSV files matching:

```
{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv
```

Valid timeframes: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`, `1w`.

### Scenario Components

Each scenario combines:

| Component | Values | Description |
|-----------|--------|-------------|
| Asset | From data files | e.g., BTC, ETH, SOL, DOGE |
| Timeframe | From data files | e.g., 1d, 4h, 15m |
| Strategy type | 5 types | trend_following, momentum, volatility, breakout, mean_reversion |
| Knowledge level | 3 levels | beginner, intermediate, advanced |

### Knowledge Level Behavior

- **Beginner**: Simple language, defers to the copilot, conservative risk.
  Goal examples: "I want a trend-following strategy for BTC on the daily
  timeframe. Keep it simple."

- **Intermediate**: Knows common indicators, specifies preferences.
  Goal examples: "I'm looking for a momentum strategy for ETH on 4-hour
  bars. I'd like to use RSI as part of the strategy."

- **Advanced**: Precise technical language, specific signal requirements.
  Goal examples: "Build me a mean-reversion strategy for SOL on 5-minute
  bars. Use complementary entry signals -- a crossover trigger with a
  momentum filter."

### Reproducibility

Same `--seed` value produces the same scenario list. The seed controls:
- Which (asset, timeframe) pairs are selected
- Which strategy types and knowledge levels are assigned
- Which detail fragments are appended to the goal string

---

## Judge Scoring

After each conversation completes, one or more judge models score the full
transcript against a 7-criterion rubric.

### Scoring Criteria (1-5 scale)

| Criterion | What It Measures |
|-----------|-----------------|
| **Intent Comprehension** | Did the copilot correctly understand asset, strategy type, timeframe, and risk? |
| **Signal Selection Quality** | Were chosen signals appropriate for the stated strategy type? |
| **Parameter Reasonableness** | Were signal parameters sensible for the asset and timeframe? |
| **Conversation Quality** | Was the conversation natural, concise, and well-structured? |
| **Guardrail Compliance** | Did the copilot stay within system rules (valid transitions, correct JSON, etc.)? |
| **Efficiency** | Did the copilot complete the task in a reasonable number of turns? |
| **Error Recovery** | How well did the copilot handle errors or unexpected inputs? |

### Self-Judging

By default, the benchmarked model also judges its own conversation
(`is_self_judge=True` in the output). This enables analysis of self-assessment
bias -- do models rate themselves higher than external judges?

Disable with `--no-self-judge`.

### Judge Input

Each judge receives:
- The original scenario goal and knowledge level
- The full conversation transcript (user + assistant, with state annotations)
- The final copilot state
- The produced strategy config JSON (if any)
- The backtest results (if any)
- Automated metrics (turns, tokens, cost, tool calls, etc.)

The judge returns structured JSON with scores, a qualitative summary,
strengths, weaknesses, and notable observations.

---

## Resume and Checkpointing

The benchmark saves a checkpoint after every (model, scenario) pair. If
interrupted (Ctrl+C, container restart, power loss), resume with:

```bash
docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
    python run_benchmark.py --resume
```

This finds the latest `run_*` directory, loads the checkpoint, and skips
already-completed pairs. Partial results (summary.csv, judge_scores.csv,
raw_results.json) are also saved incrementally, so you can inspect progress
while the benchmark runs.

### Safety: Model Restoration

The benchmark saves the original `copilot_main` model before starting and
registers an `atexit` handler to restore it. Even if the benchmark crashes,
the original model is restored on process exit.

---

## Module Reference

| File | Purpose |
|------|---------|
| `run_benchmark.py` | CLI entry point and orchestrator. Manages the model x scenario loop, judge scoring, checkpointing, and output. |
| `driver.py` | Conversation driver. Creates a copilot session, runs the user agent + state machine turn loop, captures per-turn metrics. Includes stuck-state detection (aborts after 5 consecutive 0-token turns in the same state). |
| `scenario_generator.py` | Random scenario generation. `Scenario` dataclass and `generate_scenarios(n, seed, assets)` function. Discovers available asset/timeframe pairs from data files. |
| `user_agent.py` | User agent LLM wrapper. `get_user_message(scenario_goal, knowledge_level, history, model)` generates the next user message. Uses the skill template at `skills/user_agent.md`. |
| `judge.py` | Judge agent. `score_transcript(...)` scores a completed conversation using one or more judge models. Parses structured JSON responses. Uses the skill template at `skills/judge.md`. |
| `model_switcher.py` | Database model switching. `switch_copilot_main(provider, model)` updates the `llm_model_configs` table and invalidates the in-process cache. `load_eligible_models()` queries the `llm_models` table with exclusion filters. |
| `data_loader.py` | Data file discovery. Scans the data directory for OHLCV CSVs matching `{asset}_{date}_{date}_{tf}.csv` and returns available (asset, timeframe) pairs. |
| `results.py` | Dataclasses (`TurnResult`, `JudgeScore`, `ConversationResult`, `ModelResult`, `BenchmarkRun`) and I/O functions (JSON, CSV, checkpoint). |
| `conversations.py` | Legacy scripted conversation scenarios (superseded by scenario_generator + user_agent in v2.0, retained for reference). |
| `skills/user_agent.md` | Prompt template for the user agent persona. Defines behavior rules and response format. |
| `skills/judge.md` | Prompt template for the judge scoring rubric. Defines the 7 criteria and JSON response format. |

---

## Configuration

### Model Exclusions

`model_switcher.py` excludes these model categories by default:

- **Responses API models**: `gpt-5.1-codex-max`, `gpt-5.1-codex`,
  `gpt-5.2-codex`, `gpt-5-codex` (incompatible with Chat Completions)
- **Chat-latest aliases**: Duplicates of base models
- **Embedding models**: `text-embedding-3-small`, `text-embedding-3-large`
- **Vision-only**: `grok-2-vision-1212`
- **Not in litellm**: `MiniMax-M2.5-highspeed`, `MiniMax-M2.1`
- **Pro-tier** (opt-in via `--include-pro`): `gpt-5.2-pro`, `gpt-5-pro`
- **Previous-gen** (opt-in via `--include-previous-gen`):
  `claude-opus-4-5-20251101`, `claude-sonnet-4-5-20250929`

### Fixed Models

These models are NOT varied during the benchmark:

| Call Site | Model | Rationale |
|-----------|-------|-----------|
| `copilot_meta` | Current DB setting | Title gen, KB doc selection, JSON repair |
| `embedding` | Current DB setting | Signal intent matching |
| User agent | `openai/gpt-4.1-nano` (default) | Cheap, fast, consistent |

Only `copilot_main` is switched between models.

### Defaults

| Setting | Default | Override |
|---------|---------|----------|
| Scenarios | 3 | `--n-scenarios` |
| Seed | 42 | `--seed` |
| Max turns | 20 | `--max-turns` |
| Turn timeout | 180s | `--timeout` |
| Model switch delay | 5s | `--delay` |
| User agent | `openai/gpt-4.1-nano` | `--user-agent-model` |
| Judge | `anthropic/claude-sonnet-4-6` | `--judges` |
| Self-judge | Enabled | `--no-self-judge` |

---

## Troubleshooting

### "No copilot_main row in llm_model_configs"

The `llm_model_configs` table is empty. Run the migrations (they run
automatically on container startup) or verify the database is accessible.

### "No data files found"

No CSV files in `/app/MangroveAI/data/` match the expected naming convention.
Verify files exist and follow the `{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{tf}.csv`
format.

### Model switch fails for a specific model

The model may not be in litellm's model map, or the provider API key may be
missing. Check the error message -- it will say which model failed. The
benchmark records the error and continues to the next model.

### Conversations timing out

Increase `--timeout` (default 180s). Some models are slower, especially on
complex scenarios. The stuck-state detector will also abort conversations
where the copilot produces 5 consecutive 0-token turns in the same state.

### Judge returns composite_score = 0

The judge model failed to return valid JSON. Check the `judge_error` column
in `judge_scores.csv`. Common causes: the judge model hit a rate limit,
returned markdown-wrapped JSON that couldn't be parsed, or the model is not
available.

### Container not running

```bash
cd /path/to/MangroveAI && docker compose up -d
```

Wait for migrations to complete before running the benchmark.

---

## Future Work

### Analysis Notebook

Build a Jupyter notebook for benchmark result analysis:
- Model comparison radar charts (7 criteria per model)
- Cost vs quality scatter plots
- Per-asset and per-timeframe breakdowns
- Self-judge bias analysis (self-judge score vs external judge score)
- Token efficiency analysis (tokens per successful strategy)
- Judge agreement metrics (inter-judge correlation)

### Weighted Scoring

The current composite score is an unweighted mean of all 7 criteria. Future
versions should support configurable weights (e.g., guardrail compliance may
matter more than efficiency for production use).

### Parallel Execution

Currently runs conversations sequentially. Could parallelize across models
(each model gets its own copilot session) or across scenarios within a model.
Requires careful handling of the shared `copilot_main` config -- may need
per-session model injection instead of DB-level switching.

### Multi-Turn Judge

Score individual turns in addition to the full transcript. This would enable
identifying specific failure points (e.g., which turn did the model go
off-track) rather than only final-quality assessment.

### Prompt Version Comparison

Benchmark the same model across different prompt versions
(`state_prompts_v1.json` vs `state_prompts_v2.json` vs future versions).
Would require parameterizing the prompt version in the driver.

### User Agent Diversity

Test with multiple user agent models or temperature settings to assess
copilot robustness to different user interaction styles.

### Regression Testing

Run the benchmark on a schedule (e.g., after prompt changes or model updates)
and compare against baseline results. Flag regressions in composite score
or completion rate.

### Cost Tracking for Full Pipeline

Currently tracks copilot token costs but not user agent or judge costs.
Future versions should track all LLM costs for full pipeline economics.

### ELO Rating System

Replace absolute scoring with relative rankings. Run pairwise comparisons
and compute ELO ratings across models, similar to the Chatbot Arena approach.

### Strategy Quality Validation

Beyond judge scores, validate the produced strategy configs against domain
rules:
- Are signal parameters within metadata bounds?
- Does the strategy use appropriate signal types (TRIGGER + FILTER)?
- How does the backtested Sharpe ratio compare across models?
