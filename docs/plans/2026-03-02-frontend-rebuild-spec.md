# Frontend Rebuild Specification

Date: 2026-03-02
Status: Ready for implementation
Priority: HIGH -- user's 300K experiment is running, needs to view results

## What Exists

- FastAPI backend at port 5100 (22 endpoints, 87+ tests, all working)
- HTML dashboard at `/old` (Configure view works, Explore view is basic)
- React scaffold at `experiment_ui/` (broken styling, incomplete views)
- API docs at `/docs`

## What the User Needs

### 1. Explore View (HIGHEST PRIORITY)

**Results table**: Run #, Asset, Timeframe, Start Date, End Date, Days,
Trades, Win Rate, Return%, Sharpe, Sortino, Max DD, Calmar, Net PnL,
Start Bal, End Bal, Status. Sortable columns, filterable, paginated.

**Inline row expansion**: Click a row and it expands IN PLACE (accordion
style, NOT a separate panel below the table). The expanded area shows:

- **Metrics cards** -- key numbers in a grid
- **Entry Signals** -- each signal as a card with TRIGGER/FILTER badge,
  name, timeframe, and ALL parameter name=value pairs
- **Exit Signals** -- same format, or "None (SL/TP from exec config)"
- **Execution Config** -- grouped into sections:
  - Risk Management: reward_factor, max_risk_per_trade, stop_loss_calculation
  - ATR Settings: atr_period, atr_volatility_factor, atr_short_weight, atr_long_weight
  - Position Limits: max_open_positions, max_trades_per_day, max_units, max_amount, initial_balance
  - Volatility: volatility_window, target_volatility, volatility_mode, enable_volatility_adjustment
  - Trading Rules: cooldown_bars, daily/weekly_momentum_limit
  - Time Exits: max_hold_bars, exit_on_loss_after_bars, exit_on_profit_after_bars, profit_threshold_pct
  - Costs: slippage_pct, fee_pct
- **Provenance** -- data file path, file hash, file rows, RNG seed, code version
- **"View Run" button** -- opens the run visualization

### 2. Run Visualization (opens in new tab or overlay)

When user clicks "View Run":

1. Call `GET /api/v1/experiments/{id}/results/{run_index}/visualize`
2. The backend reconstructs the strategy config and re-runs the backtest
3. Trade results are cached in Redis (TTL 1 hour)
4. Display:
   - **OHLCV candlestick chart** using `lightweight-charts` library
   - **Signal overlays** on the chart (trigger + filter lines)
   - **Trade markers** on the chart (entry arrows up, exit arrows down)
   - **Trade history table** below the chart (entry/exit price, P&L,
     exit reason, bars held, entry/exit timestamps)
   - **Strategy config summary** sidebar

**Backend changes needed for this:**
- The `/visualize` endpoint currently returns reconstructed config but
  empty trades array. Need to:
  1. Reconstruct strategy config from the result row
  2. Load OHLCV data for the asset/timeframe
  3. Re-run the backtest with the exact config (using stored RNG seed)
  4. Cache the trade results in Redis: key `exp:{id}:trades:{run_index}`, TTL 1hr
  5. Return: OHLCV data (for chart), signal series (for overlays), trades array
  6. Also return the signal evaluation timeseries so they can be plotted

### 3. Styling

**Brand colors** (from `branding/brand-guidelines.md`):
- Dark mode bg: #0C0D10 (softened black)
- Surface: #16171D
- Elevated: #1E2028
- Border: #2E3140
- Accent blue: #42A7C6 (interactive elements)
- Accent orange: #FF9E18 (FILTER badges, warnings)
- Accent red: #FF4713 (errors, negative values)
- Text: #E8EAF0
- Dim text: #8B8FA3

**Light mode**: swap to white/gray palette. Use CSS custom properties
on `:root` with `[data-theme="light"]` selector.

**Fonts**: JetBrains Mono (from Google Fonts) for all data values.
System fonts for UI text. Do NOT use Geist (not on Google Fonts).

**Color rules**: Never pair accent colors with each other (blue + orange
adjacent). Always separate with dark background.

### 4. Configure View

Port from the HTML dashboard (`/old`). Same collapsible sections, same
controls. Add proper Mangrove styling.

### 5. Monitor View

Experiment list + progress. Poll every 5 seconds. Show per-dataset
progress bars, rate, ETA.

## Technology Decision

Use whatever approach gets this done fastest and best:
- Single HTML files (like the current `/old` dashboard) -- fast, no build step
- React + Vite (existing scaffold) -- more structured, but Tailwind v4 issues
- The user doesn't care about the technology, they care about the UX

## API Endpoints Available

```
GET  /api/v1/datasets
GET  /api/v1/signals
GET  /api/v1/exec-config/defaults
GET  /api/v1/experiments
POST /api/v1/experiments
GET  /api/v1/experiments/{id}
POST /api/v1/experiments/{id}/validate
POST /api/v1/experiments/{id}/launch
POST /api/v1/experiments/{id}/pause
GET  /api/v1/experiments/{id}/results?sort=X&order=Y&limit=N&offset=M&status=S&asset=A&min_trades=T
GET  /api/v1/experiments/{id}/results/{run_index}/visualize
GET  /api/v1/experiments/{id}/progress (SSE)
```

## Key Files

- `experiment_server/app.py` -- FastAPI app, serves HTML + React
- `experiment_server/routes/results.py` -- results query + visualize endpoints
- `experiment_server/services/query.py` -- DuckDB queries
- `experiment_server/services/reconstruct.py` -- strategy config reconstruction
- `dashboard.html` -- old Configure view (working)
- `explore.html` -- old Explore view (basic)
- `experiment_ui/` -- React scaffold (broken styling)
- `experiment_ui_dist/` -- built React assets
