# Market Simulator

## Overview

An agent-based market simulator that produces synthetic price, volume, and liquidity
time series through the interaction of heterogeneous trading agents with a shared
liquidity pool. The simulator is built as a Jupyter notebook for rapid iteration and
visual analysis.

## Purpose

Generate realistic synthetic market data for use in:
- Strategy backtesting (controlled environments with known market conditions)
- Stress testing (extreme scenarios, liquidity crises, regime changes)
- Signal validation (do signals behave as expected under known conditions?)
- Agent behavior analysis (which agent types profit in which conditions?)
- Understanding market microstructure (how volume, liquidity, and price interact)

This is NOT a forecasting tool. It produces plausible market dynamics given a set
of assumptions about agent behavior and market microstructure. The goal is coherent
synthetic data, not prediction.

## Goals

1. **Coherent dynamics**: Volume drives price (not the reverse). Liquidity is consumed
   by trading and replenishes over time. Price impact follows empirically grounded
   square-root scaling.

2. **Emergent behavior**: No hardcoded price paths. Price emerges from the aggregate
   actions of many agents with different biases, risk tolerances, and thresholds.

3. **Controllable conditions**: The user specifies a market condition (bullish, bearish,
   neutral) that sets the exogenous drift. Agent behavior and environmental noise produce
   the actual realized path, which will deviate from the drift.

4. **Consistent framework**: All agents follow the same MDP structure. Signal computation
   is deterministic for every agent type. The only agent-level stochasticity is
   epsilon-greedy action selection (2% random actions), applied uniformly.

5. **Extensible**: New agent types can be added by defining signal weights. New assets
   can be added by calibrating an AssetConfig. The framework supports future additions
   like institutional vs retail agent classes, time-varying conditions, and multi-asset
   correlation.

## Architecture

### MDP Framework

Every agent operates as a stateless Markov Decision Process:

- **State**: (position, unrealized_pnl_pct, size, cash, realized_pnl) plus the
  previous bar's open-to-close return and the market condition label. All values
  are current-bar, computed by the engine.

- **Action**: {LONG, SHORT, FLAT} -- the desired position. The engine computes the
  trade required to move from the current position to the desired one.

- **Policy**: Deterministic mapping from state to preferred action. The agent computes
  a directional signal from its bias weights applied to the market condition and recent
  return, then maps that signal to a position through threshold comparison.

- **Action selection**: Epsilon-greedy. With probability 0.98, the agent takes its
  policy action. With probability 0.02, it takes a uniformly random action. This is
  the only source of agent-level stochasticity.

- **No history**: Agents do not look back. They respond to current-bar observables only.

### Agent Types

| Bias | Population % | Signal weights | Description |
|------|-------------|----------------|-------------|
| Trend follower | 30% | 0.6 * condition + 0.4 * return | Aligns with macro drift and recent movement |
| Mean reverter | 15% | 0.2 * condition - 0.8 * return | Fades recent moves, bets on pullbacks |
| Momentum | 25% | 1.0 * return | Pure price-chaser, ignores macro condition |
| Contrarian | 15% | -0.7 * condition - 0.3 * return | Opposes prevailing direction |
| Passive | 15% | 0.3 * condition | Weak directional lean, mostly inactive |

Each agent also has individualized parameters drawn from its per-agent RNG at
population creation time:
- `risk_tolerance`: beta(2,3) distribution, affects position sizing
- `entry_threshold`: uniform, higher = needs stronger signal to trade
- `stop_loss_pct` / `take_profit_pct`: scaled by risk tolerance
- `max_position_pct`: max fraction of capital to allocate

### Price Formation

The square-root impact model (Kyle 1985, Almgren-Chriss 2000):

```
price_return = drift + impact_coeff * sign(Q) * sqrt(|Q| / L) * sigma + noise
```

Where:
- `drift` = exogenous hourly expected return from market condition
- `Q` = net order flow (buy volume - sell volume) from all agent trades
- `L` = current liquidity depth
- `sigma` = asset-specific hourly volatility
- `noise` ~ N(0, sigma)

Volume is the input (agents generate orders). Price change is the output of that
volume hitting the liquidity pool. This is the causal direction: volume drives price.

### Liquidity

A pool that represents market depth. Properties:
- Consumed by trading activity (10% of total volume per bar)
- Mean-reverts toward a baseline at an asset-specific recovery rate
- Floor at 10% of base liquidity (prevents divide-by-zero and models crisis)
- When liquidity is thin, the same order flow produces larger price moves

### Assets

Four assets with calibrated parameters approximating real-world hourly behavior:

| Asset | Symbol | Initial Price | Hourly Vol | Base Liquidity |
|-------|--------|--------------|------------|----------------|
| Bitcoin | BTC | $67,000 | 0.70% | 500 |
| Gold | XAU | $2,350 | 0.18% | 800 |
| Meta Platforms | META | $500 | 0.50% | 600 |
| Crude Oil | CL | $78 | 0.30% | 700 |

All assets trade 24/7 in the simulator (simplification for uniform time structure).

### Engine Bookkeeping vs Agent State

The engine maintains `entry_prices` (a dict mapping agent_id to their position's
entry price). This is NOT part of agent state. The engine uses it each bar to
compute `unrealized_pnl_pct`, which it writes into the agent's observable state
before the agent's policy runs. The agent never sees or stores entry_price directly.

This enforces the MDP boundary: the agent observes a current-bar percentage, not
a historical price from a past action.

## Current Implementation

The simulator lives in `market_simulator.ipynb` with the following structure:

1. **Imports and config** (cell 1)
2. **Asset configuration** (cells 2-3): AssetConfig dataclass, ASSETS dict
3. **Agent framework** (cells 4-5): Position, AgentBias, AgentState, Agent, population creator
4. **Market engine** (cells 6-7): BarData, MarketEngine with square-root impact
5. **Simulation runner** (cells 8-9): SimulationResult dataclass, run_simulation function
6. **Visualization** (cells 10-11): 5-panel plots (price, volume, liquidity, net flow, positions)
7. **Scenarios** (cells 12-18): Individual asset/condition runs
8. **Cross-asset comparison** (cells 19-22): All 4 assets under same condition
9. **P&L analysis by bias** (cells 23-25): Per-bias-type P&L distributions
10. **Sensitivity analysis** (cells 26-27): Agent count effect
11. **Scratchpad** (cells 28-29): User experimentation

## Simulation Parameters

- **n_agents**: 100-1000 (default 500)
- **n_days**: default 60 (= 1440 hourly bars)
- **seed**: controls both population creation RNG and engine noise RNG
- **market_condition**: BULLISH, BEARISH, or NEUTRAL (constant for entire run)
- **epsilon**: 0.02 (2% random action probability, uniform across all agents)

## Known Limitations / Future Work

- Market condition is constant for the entire simulation. Time-varying regimes
  (e.g., 30 days bullish then 30 days bearish) are not yet supported.
- All agents are the same "class" (retail-scale). Institutional agents with
  larger capital and different risk parameters would add realism.
- No transaction costs or slippage beyond the impact model.
- No multi-asset correlation (each asset is simulated independently).
- No order book -- the liquidity pool is an abstraction, not a limit order book.
- Circuit breakers are simple per-bar caps (10%), not exchange-style halts.
- Agent capital is not depleted by losses (no bankruptcy/margin calls).
