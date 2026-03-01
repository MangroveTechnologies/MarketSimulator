"""
Random scenario generator for copilot benchmarking.

Generates conversation goals by sampling from available data files, strategy
types, and complexity levels. Each scenario is a goal string that the user
agent follows during the conversation.

Asset/timeframe pairs are discovered dynamically from the data directory
by scanning for files matching the naming convention:
    {asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

from data_loader import get_asset_timeframes


STRATEGY_TYPES = [
    "trend_following",
    "momentum",
    "volatility",
    "breakout",
    "mean_reversion",
]

KNOWLEDGE_LEVELS = ["beginner", "intermediate", "advanced"]

# Timeframe display names for natural language
TF_DISPLAY = {
    "1m": "1-minute",
    "5m": "5-minute",
    "15m": "15-minute",
    "30m": "30-minute",
    "1h": "1-hour",
    "4h": "4-hour",
    "1d": "daily",
    "1w": "weekly",
}

# Strategy type display names
STRATEGY_DISPLAY = {
    "trend_following": "trend-following",
    "momentum": "momentum",
    "volatility": "volatility",
    "breakout": "breakout",
    "mean_reversion": "mean-reversion",
}

# Extra detail fragments by complexity level
BEGINNER_DETAILS = [
    "",
    "Keep it simple.",
    "I'm new to trading.",
    "Something straightforward please.",
]

INTERMEDIATE_DETAILS = [
    "",
    "I'd like to use RSI as part of the strategy.",
    "Include some kind of moving average.",
    "I want moderate risk with decent trade frequency.",
    "Consider using Bollinger Bands.",
    "I'd like a volume-based filter.",
]

ADVANCED_DETAILS = [
    "I want tight risk management with low max drawdown.",
    "Use complementary entry signals -- a crossover trigger with a "
    "momentum filter.",
    "I want at least 2 entry conditions with volume confirmation.",
    "Optimize for Sharpe ratio. I care more about consistency than "
    "raw returns.",
    "Use a mean-reversion approach with RSI oversold as the trigger "
    "and Bollinger Band lower breakout as confirmation.",
    "I want a breakout strategy with ATR-based volatility filtering.",
]


@dataclass
class Scenario:
    """A generated benchmark scenario.

    Attributes:
        id: Unique identifier for this scenario (e.g., "s_0042").
        asset: Asset symbol (e.g., "BTC").
        timeframe: Timeframe string (e.g., "1d").
        strategy_type: One of the 5 valid strategy types.
        knowledge_level: beginner, intermediate, or advanced.
        goal: The full goal string for the user agent.
    """
    id: str
    asset: str
    timeframe: str
    strategy_type: str
    knowledge_level: str
    goal: str


def generate_scenarios(
    n: int,
    seed: int = 42,
    assets: Optional[List[str]] = None,
    data_dir: Optional[str] = None,
) -> List[Scenario]:
    """Generate N random benchmark scenarios.

    Asset/timeframe pairs are discovered from the data directory by scanning
    for CSV files matching ``{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{tf}.csv``.

    Args:
        n: Number of scenarios to generate.
        seed: Random seed for reproducibility.
        assets: Optional list of asset symbols to restrict to.
        data_dir: Optional data directory path override (defaults to
            ``/app/MangroveAI/data``, where OHLCV files live).

    Returns:
        List of Scenario objects with unique IDs.

    Raises:
        ValueError: If no data files are found or no files match the
            requested asset filter.
    """
    rng = random.Random(seed)

    # Discover available asset/timeframe combos from data files
    kwargs = {}
    if data_dir:
        kwargs["data_dir"] = data_dir
    pool = get_asset_timeframes(**kwargs)

    if not pool:
        raise ValueError(
            "No data files found matching the expected format: "
            "{asset}_{YYYY-MM-DD}_{YYYY-MM-DD}_{timeframe}.csv"
        )

    if assets:
        upper = {a.upper() for a in assets}
        pool = [(a, tf) for a, tf in pool if a in upper]
        if not pool:
            all_assets = sorted(set(a for a, _ in get_asset_timeframes(**kwargs)))
            raise ValueError(
                f"No data available for assets: {assets}. "
                f"Available: {all_assets}"
            )

    scenarios = []
    for i in range(n):
        asset, timeframe = rng.choice(pool)
        strategy_type = rng.choice(STRATEGY_TYPES)
        knowledge_level = rng.choice(KNOWLEDGE_LEVELS)

        tf_name = TF_DISPLAY.get(timeframe, timeframe)
        strat_name = STRATEGY_DISPLAY.get(strategy_type, strategy_type)

        # Build the goal string
        if knowledge_level == "beginner":
            detail = rng.choice(BEGINNER_DETAILS)
            goal = (
                f"I want a {strat_name} strategy for {asset} on the "
                f"{tf_name} timeframe. {detail}"
            ).strip()
        elif knowledge_level == "intermediate":
            detail = rng.choice(INTERMEDIATE_DETAILS)
            goal = (
                f"I'm looking for a {strat_name} strategy for {asset} on "
                f"{tf_name} bars. {detail}"
            ).strip()
        else:  # advanced
            detail = rng.choice(ADVANCED_DETAILS)
            goal = (
                f"Build me a {strat_name} strategy for {asset} on "
                f"{tf_name} bars. {detail}"
            ).strip()

        scenarios.append(Scenario(
            id=f"s_{i:04d}",
            asset=asset,
            timeframe=timeframe,
            strategy_type=strategy_type,
            knowledge_level=knowledge_level,
            goal=goal,
        ))

    return scenarios
