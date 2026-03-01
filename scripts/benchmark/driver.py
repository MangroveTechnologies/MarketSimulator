"""
Conversation driver for copilot benchmarking.

Drives agent-driven conversations through the state machine synchronously
(no Flask context, no background threads). Each turn:
  1. Calls the user agent LLM to generate the next user message.
  2. Feeds that message to the copilot state machine.
  3. Captures per-turn metrics.
"""

from __future__ import annotations

import sys
import time
import signal
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, "/app")

from MangroveAI.domains.ai_copilot.services import (
    create_conversation,
    get_context_store,
    get_state_machine,
)

from results import TurnResult
from scenario_generator import Scenario
from user_agent import get_user_message


class TurnTimeout(Exception):
    """Raised when a single turn exceeds the timeout."""


def _timeout_handler(signum, frame):
    raise TurnTimeout("Turn exceeded timeout")


def drive_conversation(
    scenario: Scenario,
    org_id: str,
    user_id: str,
    timeout_per_turn: int = 180,
    max_turns: int = 20,
    user_agent_model: str = "openai/gpt-4.1-nano",
) -> Tuple[List[TurnResult], str, Dict, Dict, Optional[str]]:
    """Drive an agent-driven conversation and collect per-turn metrics.

    The user agent LLM generates each user message based on the scenario
    goal and conversation history. The copilot state machine processes
    each message and produces assistant responses.

    Args:
        scenario: The benchmark scenario with goal and knowledge level.
        org_id: Organization UUID for the copilot session.
        user_id: User UUID for the copilot session.
        timeout_per_turn: Max seconds per copilot turn before aborting.
        max_turns: Maximum conversation turns before stopping.
        user_agent_model: litellm model string for the user agent.

    Returns:
        Tuple of ``(turns, session_id, strategy_config, backtest_results,
        error)`` where ``turns`` is a list of ``TurnResult`` objects.
    """
    # Create a fresh conversation
    conv = create_conversation(org_id=org_id, user_id=user_id)
    session_id = conv["session_id"]

    context_store = get_context_store()
    state_machine = get_state_machine()

    turns: List[TurnResult] = []
    conversation_error: Optional[str] = None

    # Get initial context
    context = context_store.get_or_create_context(
        session_id=session_id, org_id=org_id, user_id=user_id
    )

    # Track conversation history for the user agent (clean role/content only)
    agent_history: List[Dict[str, str]] = []

    # User agent token tracking
    total_user_agent_tokens = {"input": 0, "output": 0}

    # Stuck state detection: if the copilot stays in the same state for
    # too many consecutive turns it's likely hitting a silent error loop.
    MAX_STUCK_TURNS = 5
    stuck_count = 0
    last_state = None

    for turn_index in range(max_turns):
        # ---------------------------------------------------------------
        # 1. Generate user message via user agent LLM
        # ---------------------------------------------------------------
        try:
            user_message, ua_metadata = get_user_message(
                scenario_goal=scenario.goal,
                knowledge_level=scenario.knowledge_level,
                conversation_history=agent_history,
                model=user_agent_model,
            )
        except Exception as exc:
            conversation_error = f"User agent error on turn {turn_index}: {exc}"
            break

        if not user_message:
            conversation_error = f"User agent returned empty message on turn {turn_index}"
            break

        # Track user agent token costs
        ua_tokens = ua_metadata.get("token_usage", {})
        total_user_agent_tokens["input"] += ua_tokens.get("input_tokens", 0)
        total_user_agent_tokens["output"] += ua_tokens.get("output_tokens", 0)

        state_before = context.current_mode
        turn_start = time.time()

        # ---------------------------------------------------------------
        # 2. Feed message to copilot state machine
        # ---------------------------------------------------------------
        context.user_input = user_message
        context.conversation_history.append({
            "role": "user",
            "content": user_message,
            "state": context.current_mode,
        })

        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(timeout_per_turn)
            try:
                context = state_machine.execute(context)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except TurnTimeout:
            turns.append(TurnResult(
                turn_index=turn_index,
                user_message=user_message,
                state_before=state_before,
                state_after=state_before,
                wall_clock_ms=timeout_per_turn * 1000,
                error=f"Turn timed out after {timeout_per_turn}s",
            ))
            conversation_error = f"Timeout on turn {turn_index}"
            break
        except Exception as exc:
            wall_ms = int((time.time() - turn_start) * 1000)
            turns.append(TurnResult(
                turn_index=turn_index,
                user_message=user_message,
                state_before=state_before,
                state_after=state_before,
                wall_clock_ms=wall_ms,
                error=str(exc)[:500],
            ))
            conversation_error = str(exc)[:500]
            break

        wall_ms = int((time.time() - turn_start) * 1000)

        # ---------------------------------------------------------------
        # 3. Capture per-turn metrics
        # ---------------------------------------------------------------
        token_usage = {}
        if hasattr(context, "llm_response_metadata") and context.llm_response_metadata:
            token_usage = context.llm_response_metadata.get("token_usage") or {}

        tools_used = []
        if hasattr(context, "llm_response_metadata") and context.llm_response_metadata:
            tools_used = context.llm_response_metadata.get("used_tools") or []

        response_preview = ""
        assistant_response = ""
        if context.agent_response:
            response_preview = context.agent_response[:500]
            assistant_response = context.agent_response

        turns.append(TurnResult(
            turn_index=turn_index,
            user_message=user_message,
            state_before=state_before,
            state_after=context.current_mode,
            wall_clock_ms=wall_ms,
            input_tokens=token_usage.get("input_tokens", 0),
            output_tokens=token_usage.get("output_tokens", 0),
            total_tokens=token_usage.get("total_tokens", 0),
            tools_used=list(tools_used) if tools_used else [],
            assistant_response_preview=response_preview,
        ))

        # Update agent history for next user agent call
        agent_history.append({"role": "user", "content": user_message})
        if assistant_response:
            agent_history.append({"role": "assistant", "content": assistant_response})

        # Save context to DB after each turn
        context.processing_status = "complete"
        context_store.save_context(session_id, context, org_id, user_id)

        # Check terminal state
        if context.current_mode == "done":
            break

        # Stuck state detection: bail if copilot is looping in same state
        # with no tokens (indicates silent error like model not found)
        if context.current_mode == last_state:
            no_tokens = (token_usage.get("input_tokens", 0) == 0
                         and token_usage.get("output_tokens", 0) == 0)
            if no_tokens:
                stuck_count += 1
            else:
                stuck_count = 0
            if stuck_count >= MAX_STUCK_TURNS:
                conversation_error = (
                    f"Stuck in {context.current_mode} for {stuck_count} turns "
                    f"with 0 tokens -- likely a model error"
                )
                break
        else:
            stuck_count = 0
        last_state = context.current_mode

    strategy_config = getattr(context, "strategy_config", {}) or {}
    backtest_results = getattr(context, "backtest_results", {}) or {}

    return turns, session_id, strategy_config, backtest_results, conversation_error
