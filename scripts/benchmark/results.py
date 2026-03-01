"""
Dataclasses and I/O for benchmark results.

Handles per-turn metrics, per-conversation aggregation, judge scores,
JSON/CSV output, and checkpoint-based resume.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TurnResult:
    """Metrics for a single user-message -> assistant-response turn."""
    turn_index: int
    user_message: str
    state_before: str
    state_after: str
    wall_clock_ms: int
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    tools_used: List[str] = field(default_factory=list)
    assistant_response_preview: str = ""
    error: Optional[str] = None


@dataclass
class JudgeScore:
    """Scores from a single judge for one conversation."""
    judge_model: str
    is_self_judge: bool
    intent_comprehension: int = 0
    signal_selection_quality: int = 0
    parameter_reasonableness: int = 0
    conversation_quality: int = 0
    guardrail_compliance: int = 0
    efficiency: int = 0
    error_recovery: int = 0
    composite_score: float = 0.0
    summary: str = ""
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    notable_observations: List[str] = field(default_factory=list)
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0
    judge_error: Optional[str] = None


@dataclass
class ConversationResult:
    """Aggregated metrics for one complete conversation."""
    scenario_id: str
    scenario_goal: str
    asset: str
    timeframe: str
    strategy_type: str
    knowledge_level: str
    session_id: str
    total_wall_clock_ms: int
    total_input_tokens: int
    total_output_tokens: int
    cost_usd: float
    num_turns: int
    final_state: str
    reached_done: bool
    produced_strategy_config: bool
    backtest_succeeded: bool
    num_tool_calls: int
    tool_call_breakdown: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None
    turns: List[TurnResult] = field(default_factory=list)
    judge_scores: List[JudgeScore] = field(default_factory=list)


@dataclass
class ModelResult:
    """All conversation results for a single model."""
    model_id: str
    provider: str
    display_name: str
    litellm_string: str
    cost_input_per_mtok: float
    cost_output_per_mtok: float
    conversations: List[ConversationResult] = field(default_factory=list)


@dataclass
class BenchmarkRun:
    """Top-level container for a full benchmark run."""
    run_id: str
    benchmark_version: str = "2.0"
    user_agent_model: str = ""
    judge_models: List[str] = field(default_factory=list)
    copilot_meta_model: str = ""
    embedding_model: str = ""
    n_scenarios: int = 0
    seed: int = 42
    started_at: str = ""
    completed_at: str = ""
    results: List[ModelResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def aggregate_conversation(
    scenario,
    session_id: str,
    turns: List[TurnResult],
    strategy_config: Dict,
    backtest_results: Dict,
    pricing: Dict[str, float],
    error: Optional[str] = None,
) -> ConversationResult:
    """Build a ConversationResult from a list of TurnResults.

    Args:
        scenario: Scenario object with id, goal, asset, timeframe, etc.
        session_id: Copilot session UUID.
        turns: Per-turn metrics collected during the conversation.
        strategy_config: Final ``WorkingContext.strategy_config``.
        backtest_results: Final ``WorkingContext.backtest_results``.
        pricing: Dict with ``cost_input_per_mtok`` and ``cost_output_per_mtok``.
        error: Top-level error string if the conversation failed.
    """
    total_input = sum(t.input_tokens for t in turns)
    total_output = sum(t.output_tokens for t in turns)
    total_wall = sum(t.wall_clock_ms for t in turns)

    cost = (
        (total_input / 1_000_000) * pricing.get("cost_input_per_mtok", 0)
        + (total_output / 1_000_000) * pricing.get("cost_output_per_mtok", 0)
    )

    tool_breakdown: Dict[str, int] = {}
    for t in turns:
        for tool in t.tools_used:
            tool_breakdown[tool] = tool_breakdown.get(tool, 0) + 1

    final_state = turns[-1].state_after if turns else "unknown"

    bt_success = False
    if backtest_results:
        bt_success = bool(backtest_results.get("success"))

    return ConversationResult(
        scenario_id=scenario.id,
        scenario_goal=scenario.goal,
        asset=scenario.asset,
        timeframe=scenario.timeframe,
        strategy_type=scenario.strategy_type,
        knowledge_level=scenario.knowledge_level,
        session_id=session_id,
        total_wall_clock_ms=total_wall,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        cost_usd=round(cost, 6),
        num_turns=len(turns),
        final_state=final_state,
        reached_done=(final_state == "done"),
        produced_strategy_config=bool(strategy_config),
        backtest_succeeded=bt_success,
        num_tool_calls=sum(tool_breakdown.values()),
        tool_call_breakdown=tool_breakdown,
        error=error,
        turns=turns,
    )


def judge_score_from_dict(data: Dict[str, Any]) -> JudgeScore:
    """Convert a judge response dict into a JudgeScore dataclass."""
    scores = data.get("scores", {})
    token_usage = data.get("judge_token_usage", {})
    return JudgeScore(
        judge_model=data.get("judge_model", "unknown"),
        is_self_judge=data.get("is_self_judge", False),
        intent_comprehension=scores.get("intent_comprehension", 0),
        signal_selection_quality=scores.get("signal_selection_quality", 0),
        parameter_reasonableness=scores.get("parameter_reasonableness", 0),
        conversation_quality=scores.get("conversation_quality", 0),
        guardrail_compliance=scores.get("guardrail_compliance", 0),
        efficiency=scores.get("efficiency", 0),
        error_recovery=scores.get("error_recovery", 0),
        composite_score=data.get("composite_score", 0.0),
        summary=data.get("summary", ""),
        strengths=data.get("strengths", []),
        weaknesses=data.get("weaknesses", []),
        notable_observations=data.get("notable_observations", []),
        judge_input_tokens=token_usage.get("input_tokens", 0),
        judge_output_tokens=token_usage.get("output_tokens", 0),
        judge_error=data.get("judge_error"),
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def ensure_output_dir(output_dir: str) -> str:
    """Create the output directory if it doesn't exist. Returns the path."""
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def write_raw_results(run: BenchmarkRun, output_dir: str) -> str:
    """Write the full benchmark run to ``raw_results.json``."""
    path = os.path.join(output_dir, "raw_results.json")
    with open(path, "w") as fh:
        json.dump(asdict(run), fh, indent=2, default=str)
    return path


def write_summary_csv(run: BenchmarkRun, output_dir: str) -> str:
    """Write one row per (model, scenario) to ``summary.csv``."""
    path = os.path.join(output_dir, "summary.csv")
    fieldnames = [
        "model", "provider", "scenario_id", "asset", "timeframe",
        "strategy_type", "knowledge_level",
        "wall_clock_ms", "input_tokens", "output_tokens", "cost_usd",
        "turns", "final_state", "reached_done", "strategy_ok",
        "backtest_ok", "tool_calls", "error",
    ]

    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for mr in run.results:
            for cr in mr.conversations:
                writer.writerow({
                    "model": mr.model_id,
                    "provider": mr.provider,
                    "scenario_id": cr.scenario_id,
                    "asset": cr.asset,
                    "timeframe": cr.timeframe,
                    "strategy_type": cr.strategy_type,
                    "knowledge_level": cr.knowledge_level,
                    "wall_clock_ms": cr.total_wall_clock_ms,
                    "input_tokens": cr.total_input_tokens,
                    "output_tokens": cr.total_output_tokens,
                    "cost_usd": cr.cost_usd,
                    "turns": cr.num_turns,
                    "final_state": cr.final_state,
                    "reached_done": cr.reached_done,
                    "strategy_ok": cr.produced_strategy_config,
                    "backtest_ok": cr.backtest_succeeded,
                    "tool_calls": cr.num_tool_calls,
                    "error": cr.error or "",
                })
    return path


def write_judge_scores_csv(run: BenchmarkRun, output_dir: str) -> str:
    """Write one row per (model, scenario, judge) to ``judge_scores.csv``."""
    path = os.path.join(output_dir, "judge_scores.csv")
    fieldnames = [
        "model", "provider", "scenario_id", "asset", "timeframe",
        "strategy_type", "knowledge_level",
        "judge_model", "is_self_judge",
        "intent_comprehension", "signal_selection_quality",
        "parameter_reasonableness", "conversation_quality",
        "guardrail_compliance", "efficiency", "error_recovery",
        "composite_score", "summary",
        "judge_input_tokens", "judge_output_tokens", "judge_error",
    ]

    with open(path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for mr in run.results:
            for cr in mr.conversations:
                for js in cr.judge_scores:
                    writer.writerow({
                        "model": mr.model_id,
                        "provider": mr.provider,
                        "scenario_id": cr.scenario_id,
                        "asset": cr.asset,
                        "timeframe": cr.timeframe,
                        "strategy_type": cr.strategy_type,
                        "knowledge_level": cr.knowledge_level,
                        "judge_model": js.judge_model,
                        "is_self_judge": js.is_self_judge,
                        "intent_comprehension": js.intent_comprehension,
                        "signal_selection_quality": js.signal_selection_quality,
                        "parameter_reasonableness": js.parameter_reasonableness,
                        "conversation_quality": js.conversation_quality,
                        "guardrail_compliance": js.guardrail_compliance,
                        "efficiency": js.efficiency,
                        "error_recovery": js.error_recovery,
                        "composite_score": js.composite_score,
                        "summary": js.summary,
                        "judge_input_tokens": js.judge_input_tokens,
                        "judge_output_tokens": js.judge_output_tokens,
                        "judge_error": js.judge_error or "",
                    })
    return path


# ---------------------------------------------------------------------------
# Checkpoint for resume
# ---------------------------------------------------------------------------

def load_checkpoint(output_dir: str) -> Dict[str, Any]:
    """Load checkpoint state from a previous run.

    Returns:
        Dict with ``completed`` (list of {model, scenario} dicts) and
        ``original_copilot_main`` (provider, model dict).
    """
    path = os.path.join(output_dir, "checkpoint.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {"completed": [], "original_copilot_main": None}


def save_checkpoint(
    output_dir: str,
    completed: List[Dict[str, str]],
    original_copilot_main: Dict[str, str],
    run: BenchmarkRun,
) -> str:
    """Save checkpoint + incremental raw results.

    Called after each (model, scenario) pair completes.
    """
    path = os.path.join(output_dir, "checkpoint.json")
    with open(path, "w") as fh:
        json.dump({
            "completed": completed,
            "original_copilot_main": original_copilot_main,
        }, fh, indent=2)

    # Also write incremental raw results so partial data is available
    write_raw_results(run, output_dir)
    write_summary_csv(run, output_dir)
    write_judge_scores_csv(run, output_dir)

    return path


def is_completed(
    completed: List[Dict[str, str]],
    model_id: str,
    scenario_id: str,
) -> bool:
    """Check if a (model, scenario) pair is already in the checkpoint."""
    for entry in completed:
        if entry.get("model") == model_id and entry.get("scenario") == scenario_id:
            return True
    return False
