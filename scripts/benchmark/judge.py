"""
Judge agent for copilot benchmarking.

Scores a conversation transcript against the 7-criterion rubric using one
or more judge models. Each judge receives the full transcript, scenario
context, and automated metrics, and returns structured scores as JSON.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, "/app")

from MangroveAI.domains.ai_copilot.llm_client import (
    _call_with_retry,
    _extract_token_usage,
)
from MangroveAI.domains.ai_copilot.services import _ensure_litellm_initialised

import litellm

# ---------------------------------------------------------------------------
# Skill prompt
# ---------------------------------------------------------------------------

_SKILL_PATH = os.path.join(os.path.dirname(__file__), "skills", "judge.md")


def _load_skill_prompt() -> str:
    """Load the judge skill markdown prompt."""
    with open(_SKILL_PATH) as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Transcript formatting
# ---------------------------------------------------------------------------

def _format_transcript(conversation_history: List[dict]) -> str:
    """Format conversation history into a readable transcript."""
    lines = []
    for i, msg in enumerate(conversation_history, 1):
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        state = msg.get("state", "")
        state_tag = f" [{state}]" if state else ""
        lines.append(f"Turn {i} ({role}{state_tag}):\n{content}\n")
    return "\n".join(lines)


def _build_judge_input(
    scenario_goal: str,
    knowledge_level: str,
    transcript: List[dict],
    final_state: str,
    strategy_config: Dict,
    backtest_results: Dict,
    automated_metrics: Dict,
) -> str:
    """Build the user message containing all judge input data."""
    sections = [
        f"## Scenario Goal\n{scenario_goal}",
        f"## Knowledge Level\n{knowledge_level}",
        f"## Transcript\n{_format_transcript(transcript)}",
        f"## Final State\n{final_state}",
        f"## Strategy Config\n```json\n{json.dumps(strategy_config, indent=2, default=str) if strategy_config else '(none)'}\n```",
        f"## Backtest Results\n```json\n{json.dumps(backtest_results, indent=2, default=str) if backtest_results else '(none)'}\n```",
        f"## Automated Metrics\n```json\n{json.dumps(automated_metrics, indent=2, default=str)}\n```",
    ]
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Score parsing
# ---------------------------------------------------------------------------

SCORE_KEYS = [
    "intent_comprehension",
    "signal_selection_quality",
    "parameter_reasonableness",
    "conversation_quality",
    "guardrail_compliance",
    "efficiency",
    "error_recovery",
]


def _parse_judge_response(text: str) -> Dict[str, Any]:
    """Parse the judge's JSON response, tolerating markdown fences.

    Returns:
        Parsed dict with scores, composite_score, summary, etc.
        On parse failure, returns a dict with error info and all scores = 0.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        cleaned = "\n".join(lines)

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return {
            "scores": {k: 0 for k in SCORE_KEYS},
            "composite_score": 0.0,
            "summary": f"Failed to parse judge response: {exc}",
            "strengths": [],
            "weaknesses": [],
            "notable_observations": [],
            "parse_error": str(exc),
            "raw_response": text[:1000],
        }

    scores = data.get("scores", {})
    valid_scores = []
    for key in SCORE_KEYS:
        val = scores.get(key, 0)
        if isinstance(val, (int, float)) and 1 <= val <= 5:
            valid_scores.append(val)
        else:
            scores[key] = 0

    if valid_scores:
        data["composite_score"] = round(sum(valid_scores) / len(valid_scores), 2)

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_transcript(
    scenario_goal: str,
    knowledge_level: str,
    conversation_history: List[dict],
    final_state: str,
    strategy_config: Dict,
    backtest_results: Dict,
    automated_metrics: Dict,
    judge_models: List[str],
    copilot_model: Optional[str] = None,
    include_self_judge: bool = True,
) -> List[Dict[str, Any]]:
    """Score a conversation transcript using one or more judge models.

    Accepts a list of judge models. If ``include_self_judge`` is True and
    ``copilot_model`` is provided, the benchmarked model is appended to the
    judge list (if not already present) so it also scores its own output.

    Args:
        scenario_goal: The original scenario goal string.
        knowledge_level: beginner, intermediate, or advanced.
        conversation_history: Full conversation as list of message dicts.
        final_state: The copilot's terminal state.
        strategy_config: The produced strategy JSON (may be empty).
        backtest_results: The backtest outcome (may be empty).
        automated_metrics: Dict with turn_count, token_usage, etc.
        judge_models: List of litellm model strings for the judges.
            A single-element list is fine for one judge.
        copilot_model: The litellm string of the model being benchmarked.
            Used to tag self-judging.
        include_self_judge: If True and copilot_model is provided, also
            have the benchmarked model judge its own conversation.

    Returns:
        List of score dicts (one per judge), each containing:
        ``scores``, ``composite_score``, ``summary``, ``strengths``,
        ``weaknesses``, ``notable_observations``, ``judge_model``,
        ``is_self_judge``, ``judge_token_usage``, ``judge_error``.
    """
    _ensure_litellm_initialised()

    # Build the full judge list
    all_judges = list(judge_models)
    if include_self_judge and copilot_model and copilot_model not in all_judges:
        all_judges.append(copilot_model)

    # Pre-build inputs (same for all judges)
    system_prompt = _load_skill_prompt()
    judge_input = _build_judge_input(
        scenario_goal=scenario_goal,
        knowledge_level=knowledge_level,
        transcript=conversation_history,
        final_state=final_state,
        strategy_config=strategy_config,
        backtest_results=backtest_results,
        automated_metrics=automated_metrics,
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": judge_input},
    ]

    results = []
    for judge_model in all_judges:
        is_self = (judge_model == copilot_model)
        try:
            resp = _call_with_retry(
                litellm.completion,
                model=judge_model,
                messages=messages,
                temperature=0.0,
                max_tokens=1500,
                response_format={"type": "json_object"},
                timeout=120,
            )

            text = (resp.choices[0].message.content or "").strip()
            token_usage = _extract_token_usage(resp) or {}

            result = _parse_judge_response(text)
            result["judge_model"] = judge_model
            result["is_self_judge"] = is_self
            result["judge_token_usage"] = token_usage
            result["judge_error"] = None
        except Exception as exc:
            result = {
                "scores": {k: 0 for k in SCORE_KEYS},
                "composite_score": 0.0,
                "summary": f"Judge call failed: {exc}",
                "strengths": [],
                "weaknesses": [],
                "notable_observations": [],
                "judge_model": judge_model,
                "is_self_judge": is_self,
                "judge_token_usage": {},
                "judge_error": str(exc)[:500],
            }
        results.append(result)

    return results
