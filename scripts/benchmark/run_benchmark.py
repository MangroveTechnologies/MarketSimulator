"""
LLM model benchmark for the MangroveAI AI copilot.

Runs agent-driven conversations across all eligible models and captures
metrics on time, cost, token usage, tool calls, and quality scores from
one or more judge models.

Architecture:
  - User agent (cheap LLM) generates user messages following a scenario goal
  - Copilot under test processes messages through its state machine
  - Judge agent(s) score each completed transcript against a 7-criterion rubric

Lives in MarketSimulator but depends on MangroveAI's copilot at runtime.
Run inside a container with both projects mounted::

    docker exec -w /app/MarketSimulator/scripts/benchmark mangrove-sweep \
        python run_benchmark.py [OPTIONS]

Usage examples::

    # Dry-run: show model x scenario matrix
    python run_benchmark.py --dry-run

    # Single model smoke test
    python run_benchmark.py --models MiniMax-M2.5 --n-scenarios 1

    # Two-model comparison
    python run_benchmark.py --models MiniMax-M2.5,gpt-4.1-mini --n-scenarios 3

    # Full benchmark with custom judges
    python run_benchmark.py --judges claude-sonnet-4-6-20260217,gpt-4.1

    # Resume after interruption
    python run_benchmark.py --resume
"""

from __future__ import annotations

import argparse
import atexit
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/app")
# Ensure the benchmark package is importable from the scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from driver import drive_conversation
from judge import score_transcript as judge_score_transcript
from model_switcher import (
    get_current_copilot_main,
    load_eligible_models,
    switch_copilot_main,
)
from results import (
    BenchmarkRun,
    ConversationResult,
    JudgeScore,
    ModelResult,
    TurnResult,
    aggregate_conversation,
    ensure_output_dir,
    is_completed,
    judge_score_from_dict,
    load_checkpoint,
    save_checkpoint,
    write_judge_scores_csv,
    write_raw_results,
    write_summary_csv,
)
from scenario_generator import Scenario, generate_scenarios

# Default user/org for benchmark conversations (from MangroveAI config)
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000002"

DEFAULT_OUTPUT_BASE = "/app/MarketSimulator/data/benchmark_results"
DEFAULT_USER_AGENT_MODEL = "openai/gpt-4.1-nano"
DEFAULT_JUDGE_MODELS = ["anthropic/claude-sonnet-4-6"]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="LLM model benchmark for the MangroveAI copilot.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--models", type=str, default=None,
        help="Comma-separated model IDs to benchmark (default: all eligible)",
    )
    parser.add_argument(
        "--n-scenarios", type=int, default=3,
        help="Number of random scenarios to generate (default: 3)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for scenario generation (default: 42)",
    )
    parser.add_argument(
        "--assets", type=str, default=None,
        help="Comma-separated asset symbols to restrict scenarios to",
    )
    parser.add_argument(
        "--judges", type=str, default=None,
        help=(
            "Comma-separated judge model IDs in litellm format "
            "(default: anthropic/claude-sonnet-4-6-20260217 + self-judge)"
        ),
    )
    parser.add_argument(
        "--no-self-judge", action="store_true",
        help="Disable self-judging (benchmarked model judging its own output)",
    )
    parser.add_argument(
        "--user-agent-model", type=str, default=DEFAULT_USER_AGENT_MODEL,
        help=f"litellm model for user agent (default: {DEFAULT_USER_AGENT_MODEL})",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from latest run's checkpoint.json",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help=f"Output directory (default: {DEFAULT_OUTPUT_BASE}/run_<timestamp>)",
    )
    parser.add_argument(
        "--include-pro", action="store_true",
        help="Include expensive pro-tier models (gpt-5.2-pro, gpt-5-pro)",
    )
    parser.add_argument(
        "--include-previous-gen", action="store_true",
        help="Include previous-generation Anthropic models",
    )
    parser.add_argument(
        "--timeout", type=int, default=180,
        help="Per-turn timeout in seconds (default: 180)",
    )
    parser.add_argument(
        "--max-turns", type=int, default=20,
        help="Max conversation turns per scenario (default: 20)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print model x scenario matrix without executing",
    )
    parser.add_argument(
        "--delay", type=int, default=5,
        help="Seconds to wait between model switches (default: 5)",
    )
    return parser.parse_args()


def find_latest_run_dir(base: str) -> str | None:
    """Find the most recent run_* directory for --resume."""
    if not os.path.isdir(base):
        return None
    dirs = sorted(
        [d for d in os.listdir(base) if d.startswith("run_")],
        reverse=True,
    )
    return os.path.join(base, dirs[0]) if dirs else None


def main() -> None:
    """Entry point for the benchmark."""
    args = parse_args()

    # ------------------------------------------------------------------
    # 1. Load model list
    # ------------------------------------------------------------------
    all_models = load_eligible_models(
        include_pro=args.include_pro,
        include_previous_gen=args.include_previous_gen,
    )

    if args.models:
        requested = [m.strip() for m in args.models.split(",")]
        model_ids = {m["id"] for m in all_models}
        invalid = [r for r in requested if r not in model_ids]
        if invalid:
            print(
                f"ERROR: Unknown model IDs: {invalid}\n"
                f"Valid: {sorted(model_ids)}",
                file=sys.stderr,
            )
            sys.exit(1)
        all_models = [m for m in all_models if m["id"] in requested]

    # ------------------------------------------------------------------
    # 2. Generate scenarios
    # ------------------------------------------------------------------
    assets_filter = None
    if args.assets:
        assets_filter = [a.strip() for a in args.assets.split(",")]

    scenarios = generate_scenarios(
        n=args.n_scenarios,
        seed=args.seed,
        assets=assets_filter,
    )

    # ------------------------------------------------------------------
    # 3. Resolve judge models
    # ------------------------------------------------------------------
    judge_models = list(DEFAULT_JUDGE_MODELS)
    if args.judges:
        judge_models = [j.strip() for j in args.judges.split(",")]

    include_self_judge = not args.no_self_judge

    total_combos = len(all_models) * len(scenarios)

    # ------------------------------------------------------------------
    # 4. Dry run
    # ------------------------------------------------------------------
    if args.dry_run:
        print(
            f"\n[DRY RUN] {len(all_models)} models x {len(scenarios)} scenarios "
            f"= {total_combos} combinations\n",
        )
        print("Models:")
        for m in all_models:
            cost_str = ""
            if m["cost_input_per_mtok"] > 0 or m["cost_output_per_mtok"] > 0:
                cost_str = f" (${m['cost_input_per_mtok']}/{m['cost_output_per_mtok']} per Mtok)"
            else:
                cost_str = " (pricing unavailable)"
            print(f"  {m['provider_id']:10s} {m['id']:40s}{cost_str}")

        print(f"\nScenarios ({len(scenarios)}):")
        for s in scenarios:
            print(
                f"  {s.id:8s} {s.asset:6s} {s.timeframe:4s} "
                f"{s.strategy_type:16s} [{s.knowledge_level:12s}]  {s.goal[:70]}..."
                if len(s.goal) > 70 else
                f"  {s.id:8s} {s.asset:6s} {s.timeframe:4s} "
                f"{s.strategy_type:16s} [{s.knowledge_level:12s}]  {s.goal}"
            )

        print(f"\nUser agent: {args.user_agent_model}")
        print(f"Judges: {judge_models}")
        if include_self_judge:
            print("  + self-judge (benchmarked model judges its own output)")
        return

    # ------------------------------------------------------------------
    # 5. Output directory and resume
    # ------------------------------------------------------------------
    if args.resume:
        output_dir = args.output or find_latest_run_dir(DEFAULT_OUTPUT_BASE)
        if not output_dir:
            print(
                "ERROR: --resume but no existing run directory found.",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_dir = args.output or os.path.join(
            DEFAULT_OUTPUT_BASE, f"run_{timestamp}"
        )

    ensure_output_dir(output_dir)

    # Load checkpoint
    checkpoint = load_checkpoint(output_dir)
    completed = checkpoint.get("completed", [])

    # ------------------------------------------------------------------
    # 6. Save original model and register restore handler
    # ------------------------------------------------------------------
    original_provider, original_model = get_current_copilot_main()
    original_copilot_main = {
        "provider": original_provider,
        "model": original_model,
    }

    if not checkpoint.get("original_copilot_main"):
        checkpoint["original_copilot_main"] = original_copilot_main

    def restore_original():
        orig = checkpoint.get("original_copilot_main", original_copilot_main)
        try:
            switch_copilot_main(orig["provider"], orig["model"])
            print(
                f"\n[BENCHMARK] Restored copilot_main to "
                f"{orig['provider']}/{orig['model']}",
                file=sys.stderr,
            )
        except Exception as e:
            print(
                f"\n[BENCHMARK] WARNING: Failed to restore copilot_main: {e}",
                file=sys.stderr,
            )

    atexit.register(restore_original)

    # ------------------------------------------------------------------
    # 7. Fetch fixed model info for metadata
    # ------------------------------------------------------------------
    from MangroveAI.domains.ai_copilot.llm_config_cache import get_model
    copilot_meta_model = get_model("copilot_meta")
    embedding_model = get_model("embedding")

    # ------------------------------------------------------------------
    # 8. Initialize run
    # ------------------------------------------------------------------
    run = BenchmarkRun(
        run_id=os.path.basename(output_dir),
        user_agent_model=args.user_agent_model,
        judge_models=judge_models,
        copilot_meta_model=copilot_meta_model,
        embedding_model=embedding_model,
        n_scenarios=args.n_scenarios,
        seed=args.seed,
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # Reload any previously completed results
    if args.resume:
        prev_raw = os.path.join(output_dir, "raw_results.json")
        if os.path.exists(prev_raw):
            import json
            with open(prev_raw) as fh:
                prev_data = json.load(fh)
            for mr_data in prev_data.get("results", []):
                mr = ModelResult(
                    model_id=mr_data["model_id"],
                    provider=mr_data["provider"],
                    display_name=mr_data["display_name"],
                    litellm_string=mr_data["litellm_string"],
                    cost_input_per_mtok=mr_data["cost_input_per_mtok"],
                    cost_output_per_mtok=mr_data["cost_output_per_mtok"],
                )
                for cr_data in mr_data.get("conversations", []):
                    cr_turns = [
                        TurnResult(**t) for t in cr_data.get("turns", [])
                    ]
                    cr = ConversationResult(
                        scenario_id=cr_data["scenario_id"],
                        scenario_goal=cr_data.get("scenario_goal", ""),
                        asset=cr_data.get("asset", ""),
                        timeframe=cr_data.get("timeframe", ""),
                        strategy_type=cr_data.get("strategy_type", ""),
                        knowledge_level=cr_data.get("knowledge_level", ""),
                        session_id=cr_data["session_id"],
                        total_wall_clock_ms=cr_data["total_wall_clock_ms"],
                        total_input_tokens=cr_data["total_input_tokens"],
                        total_output_tokens=cr_data["total_output_tokens"],
                        cost_usd=cr_data["cost_usd"],
                        num_turns=cr_data["num_turns"],
                        final_state=cr_data["final_state"],
                        reached_done=cr_data["reached_done"],
                        produced_strategy_config=cr_data["produced_strategy_config"],
                        backtest_succeeded=cr_data["backtest_succeeded"],
                        num_tool_calls=cr_data["num_tool_calls"],
                        tool_call_breakdown=cr_data.get("tool_call_breakdown", {}),
                        error=cr_data.get("error"),
                        turns=cr_turns,
                    )
                    # Restore judge scores
                    for js_data in cr_data.get("judge_scores", []):
                        cr.judge_scores.append(JudgeScore(**{
                            k: v for k, v in js_data.items()
                        }))
                    mr.conversations.append(cr)
                run.results.append(mr)

    skipped = len(completed)
    remaining = total_combos - skipped

    print(
        f"[BENCHMARK] {len(all_models)} models x {len(scenarios)} scenarios "
        f"= {total_combos} combos ({skipped} already done, {remaining} remaining)",
        file=sys.stderr,
    )
    print(f"[BENCHMARK] Output: {output_dir}", file=sys.stderr)
    print(
        f"[BENCHMARK] User agent: {args.user_agent_model}",
        file=sys.stderr,
    )
    print(
        f"[BENCHMARK] Judges: {judge_models}"
        + (" + self" if include_self_judge else ""),
        file=sys.stderr,
    )
    print(
        f"[BENCHMARK] Fixed models: meta={copilot_meta_model}, "
        f"embedding={embedding_model}",
        file=sys.stderr,
    )

    # ------------------------------------------------------------------
    # 9. Main loop
    # ------------------------------------------------------------------
    combo_index = 0
    for model_info in all_models:
        model_id = model_info["id"]
        provider = model_info["provider_id"]
        litellm_string = f"{provider}/{model_id}"
        pricing = {
            "cost_input_per_mtok": model_info["cost_input_per_mtok"],
            "cost_output_per_mtok": model_info["cost_output_per_mtok"],
        }

        # Find or create ModelResult for this model
        model_result = None
        for mr in run.results:
            if mr.model_id == model_id:
                model_result = mr
                break
        if model_result is None:
            model_result = ModelResult(
                model_id=model_id,
                provider=provider,
                display_name=model_info["display_name"],
                litellm_string=litellm_string,
                cost_input_per_mtok=model_info["cost_input_per_mtok"],
                cost_output_per_mtok=model_info["cost_output_per_mtok"],
            )
            run.results.append(model_result)

        # Check if all scenarios for this model are already done
        model_scenarios = [
            s for s in scenarios
            if not is_completed(completed, model_id, s.id)
        ]
        if not model_scenarios:
            continue

        # Switch model
        print(
            f"\n[BENCHMARK] Switching to {litellm_string}...",
            file=sys.stderr,
        )
        try:
            switch_copilot_main(provider, model_id)
        except Exception as exc:
            print(
                f"[BENCHMARK] ERROR switching to {litellm_string}: {exc}",
                file=sys.stderr,
            )
            for scenario in model_scenarios:
                cr = ConversationResult(
                    scenario_id=scenario.id,
                    scenario_goal=scenario.goal,
                    asset=scenario.asset,
                    timeframe=scenario.timeframe,
                    strategy_type=scenario.strategy_type,
                    knowledge_level=scenario.knowledge_level,
                    session_id="",
                    total_wall_clock_ms=0,
                    total_input_tokens=0,
                    total_output_tokens=0,
                    cost_usd=0,
                    num_turns=0,
                    final_state="error",
                    reached_done=False,
                    produced_strategy_config=False,
                    backtest_succeeded=False,
                    num_tool_calls=0,
                    error=f"Model switch failed: {exc}",
                )
                model_result.conversations.append(cr)
                completed.append({
                    "model": model_id,
                    "scenario": scenario.id,
                })
            save_checkpoint(
                output_dir, completed, original_copilot_main, run
            )
            continue

        time.sleep(args.delay)

        for scenario in model_scenarios:
            combo_index += 1
            if is_completed(completed, model_id, scenario.id):
                continue

            print(
                f"[BENCHMARK] [{combo_index}/{total_combos}] "
                f"{litellm_string} x {scenario.id} "
                f"({scenario.asset}/{scenario.timeframe} "
                f"{scenario.strategy_type} [{scenario.knowledge_level}])...",
                file=sys.stderr,
                flush=True,
            )

            # -----------------------------------------------------------
            # Run conversation
            # -----------------------------------------------------------
            t0 = time.time()
            try:
                turns, session_id, strategy_config, backtest_results, error = \
                    drive_conversation(
                        scenario=scenario,
                        org_id=DEFAULT_ORG_ID,
                        user_id=DEFAULT_USER_ID,
                        timeout_per_turn=args.timeout,
                        max_turns=args.max_turns,
                        user_agent_model=args.user_agent_model,
                    )
            except Exception as exc:
                turns = []
                session_id = ""
                strategy_config = {}
                backtest_results = {}
                error = f"Driver error: {str(exc)[:500]}"

            elapsed_ms = int((time.time() - t0) * 1000)

            cr = aggregate_conversation(
                scenario=scenario,
                session_id=session_id,
                turns=turns,
                strategy_config=strategy_config,
                backtest_results=backtest_results,
                pricing=pricing,
                error=error,
            )

            status = "DONE" if cr.reached_done else cr.final_state
            if cr.error:
                status = f"ERROR: {cr.error[:80]}"

            print(
                f"  -> {status} | {cr.num_turns} turns | "
                f"{elapsed_ms}ms | "
                f"{cr.total_input_tokens}+{cr.total_output_tokens} tokens | "
                f"${cr.cost_usd:.4f} | "
                f"tools={cr.num_tool_calls}",
                file=sys.stderr,
                flush=True,
            )

            # -----------------------------------------------------------
            # Judge scoring
            # -----------------------------------------------------------
            automated_metrics = {
                "num_turns": cr.num_turns,
                "total_input_tokens": cr.total_input_tokens,
                "total_output_tokens": cr.total_output_tokens,
                "cost_usd": cr.cost_usd,
                "num_tool_calls": cr.num_tool_calls,
                "tool_call_breakdown": cr.tool_call_breakdown,
                "wall_clock_ms": cr.total_wall_clock_ms,
                "reached_done": cr.reached_done,
                "produced_strategy_config": cr.produced_strategy_config,
                "backtest_succeeded": cr.backtest_succeeded,
            }

            # Build full conversation history for judges
            conv_history = []
            for turn in turns:
                conv_history.append({
                    "role": "user",
                    "content": turn.user_message,
                    "state": turn.state_before,
                })
                if turn.assistant_response_preview:
                    conv_history.append({
                        "role": "assistant",
                        "content": turn.assistant_response_preview,
                        "state": turn.state_after,
                    })

            print(
                f"  -> Scoring with {len(judge_models)} judge(s)"
                + (" + self" if include_self_judge else "") + "...",
                file=sys.stderr,
                flush=True,
            )

            try:
                judge_results = judge_score_transcript(
                    scenario_goal=scenario.goal,
                    knowledge_level=scenario.knowledge_level,
                    conversation_history=conv_history,
                    final_state=cr.final_state,
                    strategy_config=strategy_config,
                    backtest_results=backtest_results,
                    automated_metrics=automated_metrics,
                    judge_models=judge_models,
                    copilot_model=litellm_string,
                    include_self_judge=include_self_judge,
                )
                for jr in judge_results:
                    js = judge_score_from_dict(jr)
                    cr.judge_scores.append(js)
                    self_tag = " (self)" if js.is_self_judge else ""
                    print(
                        f"     {js.judge_model}{self_tag}: "
                        f"composite={js.composite_score:.1f}",
                        file=sys.stderr,
                        flush=True,
                    )
            except Exception as exc:
                print(
                    f"  -> Judge scoring failed: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

            model_result.conversations.append(cr)

            # Checkpoint after each conversation
            completed.append({
                "model": model_id,
                "scenario": scenario.id,
            })
            save_checkpoint(
                output_dir, completed, original_copilot_main, run
            )

    # ------------------------------------------------------------------
    # 10. Final output
    # ------------------------------------------------------------------
    run.completed_at = datetime.now(timezone.utc).isoformat()
    write_raw_results(run, output_dir)
    csv_path = write_summary_csv(run, output_dir)
    judge_csv_path = write_judge_scores_csv(run, output_dir)

    print(f"\n[BENCHMARK] Complete.", file=sys.stderr)
    print(f"[BENCHMARK] Results: {output_dir}", file=sys.stderr)
    print(f"[BENCHMARK] Summary: {csv_path}", file=sys.stderr)
    print(f"[BENCHMARK] Judge scores: {judge_csv_path}", file=sys.stderr)

    # Print quick summary table
    print(
        f"\n{'Model':<40s} {'Scenario':<10s} {'Done?':>6s} "
        f"{'Turns':>6s} {'Cost':>8s} {'Time':>8s} {'Score':>6s}",
        file=sys.stderr,
    )
    print("-" * 90, file=sys.stderr)
    for mr in run.results:
        for cr in mr.conversations:
            done_str = "yes" if cr.reached_done else "NO"
            if cr.error:
                done_str = "ERR"
            # Average composite across all judges
            avg_score = 0.0
            if cr.judge_scores:
                valid = [
                    js.composite_score for js in cr.judge_scores
                    if js.composite_score > 0
                ]
                if valid:
                    avg_score = sum(valid) / len(valid)
            print(
                f"{mr.litellm_string:<40s} {cr.scenario_id:<10s} "
                f"{done_str:>6s} {cr.num_turns:>6d} "
                f"${cr.cost_usd:>7.4f} "
                f"{cr.total_wall_clock_ms / 1000:>7.1f}s "
                f"{avg_score:>5.1f}",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
