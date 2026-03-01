"""
Scripted conversation scenarios for LLM model benchmarking.

Each scenario defines a sequence of user messages to drive the copilot
state machine through a complete strategy creation flow. Messages are
dispatched adaptively based on the copilot's current state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ConversationScenario:
    """A scripted conversation to benchmark against the copilot.

    Attributes:
        name: Short identifier (used in filenames and CSV output).
        complexity: Human label: "simple", "moderate", or "complex".
        description: One-line summary of the scenario.
        collect_messages: Messages to send while in ``collect_user_input``.
        confirm_plan: Message to send when the copilot presents a signal plan.
        confirm_assembly: Message to send when the copilot presents a strategy.
        confirm_backtest: Message to send to trigger or confirm backtest.
        fallback_message: Generic continuation if the copilot asks something
            unexpected.
        max_turns: Safety limit to prevent infinite loops.
    """
    name: str
    complexity: str
    description: str
    collect_messages: List[str]
    confirm_plan: str = "yes, that looks good"
    confirm_assembly: str = "yes, proceed"
    confirm_backtest: str = "yes, run the backtest"
    fallback_message: str = "yes"
    max_turns: int = 20


def get_next_message(scenario: ConversationScenario, current_mode: str,
                     turn_index: int, collect_index: int) -> Optional[str]:
    """Pick the next user message based on copilot state.

    Args:
        scenario: The active scenario.
        current_mode: The copilot's ``current_mode`` after its last response.
        turn_index: Total turns elapsed (for safety limit).
        collect_index: How many ``collect_messages`` have been sent so far.

    Returns:
        The next user message to send, or ``None`` if the conversation is
        complete (reached ``done`` or hit max turns).
    """
    if current_mode == "done":
        return None

    if turn_index >= scenario.max_turns:
        return None

    if current_mode == "collect_user_input":
        if collect_index < len(scenario.collect_messages):
            return scenario.collect_messages[collect_index]
        return scenario.fallback_message

    if current_mode == "plan_signals":
        return scenario.confirm_plan

    if current_mode == "assemble_strategy":
        return scenario.confirm_assembly

    if current_mode == "backtest":
        return scenario.confirm_backtest

    return scenario.fallback_message


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

SIMPLE = ConversationScenario(
    name="simple_rsi_btc",
    complexity="simple",
    description="Direct RSI strategy request for BTC on daily timeframe",
    collect_messages=[
        "I want a simple RSI strategy for Bitcoin on the daily timeframe",
        "skip",
        "moderate risk, let's keep it simple",
    ],
    max_turns=12,
)

MODERATE = ConversationScenario(
    name="moderate_eth_momentum",
    complexity="moderate",
    description="Vague ETH request requiring clarification rounds",
    collect_messages=[
        "I want to trade ethereum",
        "skip",
        "4 hour timeframe, looking for momentum",
        "moderate risk tolerance",
        "that sounds good",
    ],
    max_turns=15,
)

COMPLEX = ConversationScenario(
    name="complex_sol_mean_reversion",
    complexity="complex",
    description="Sophisticated multi-signal mean reversion for SOL on 5m bars",
    collect_messages=[
        "Build me a sophisticated mean-reversion strategy for SOL on "
        "5-minute bars with multiple entry conditions",
        "skip",
        "I want at least 2 entry triggers with Bollinger Bands and RSI, "
        "plus a volume filter",
        "yes that works",
    ],
    max_turns=20,
)

ALL_SCENARIOS = [SIMPLE, MODERATE, COMPLEX]
SCENARIOS_BY_NAME = {s.name: s for s in ALL_SCENARIOS}
