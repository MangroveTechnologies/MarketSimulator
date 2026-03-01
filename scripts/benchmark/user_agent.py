"""
LLM-driven user agent for copilot benchmarking.

Uses a cheap, fast model (e.g., gpt-4.1-nano) to simulate a user following
a scenario goal. Each call receives the conversation history and returns
the next user message.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, List, Tuple

sys.path.insert(0, "/app")

from MangroveAI.domains.ai_copilot.llm_client import (
    _call_with_retry,
    _extract_token_usage,
)
from MangroveAI.domains.ai_copilot.services import _ensure_litellm_initialised

import litellm

# ---------------------------------------------------------------------------
# Skill prompt template
# ---------------------------------------------------------------------------

_SKILL_PATH = os.path.join(os.path.dirname(__file__), "skills", "user_agent.md")


def _load_skill_template() -> str:
    """Load the user agent skill markdown template."""
    with open(_SKILL_PATH) as fh:
        return fh.read()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_user_message(
    scenario_goal: str,
    knowledge_level: str,
    conversation_history: List[dict],
    model: str = "openai/gpt-4.1-nano",
    temperature: float = 0.0,
    max_tokens: int = 200,
) -> Tuple[str, Dict]:
    """Generate the next user message given the conversation so far.

    Args:
        scenario_goal: The goal string from the scenario generator.
        knowledge_level: beginner, intermediate, or advanced.
        conversation_history: List of ``{"role": ..., "content": ...}`` dicts
            representing the conversation so far (user + assistant messages).
        model: litellm model string for the user agent.
        temperature: Sampling temperature (0 for reproducibility).
        max_tokens: Max tokens for the user agent response.

    Returns:
        Tuple of ``(user_message, metadata)`` where metadata contains
        token usage info.
    """
    _ensure_litellm_initialised()

    # Build system prompt from skill template
    template = _load_skill_template()
    system_prompt = template.replace(
        "{scenario_goal}", scenario_goal
    ).replace(
        "{knowledge_level}", knowledge_level
    )

    # Build messages: system prompt + recent conversation history.
    # Truncate to last 20 messages to avoid context window overflow on
    # cheap models like gpt-4.1-nano (1M token limit).
    MAX_HISTORY_MESSAGES = 20
    recent_history = conversation_history[-MAX_HISTORY_MESSAGES:]

    messages = [{"role": "system", "content": system_prompt}]
    for msg in recent_history:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    resp = _call_with_retry(
        litellm.completion,
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=30,
    )

    text = (resp.choices[0].message.content or "").strip()
    token_usage = _extract_token_usage(resp) or {}

    return text, {"token_usage": token_usage, "model": model}
