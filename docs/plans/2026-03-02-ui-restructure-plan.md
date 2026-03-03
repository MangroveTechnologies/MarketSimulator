# UI Restructure Plan

Date: 2026-03-02
Status: Ready for implementation

## Summary

Restructure the React UI to fix 3 core problems:
1. Wrong architecture: chart/trades crammed into accordion expand; should be a separate View tab
2. Slow UX: visualize endpoint (re-runs backtest) called on every row click; should only run on explicit "View Run"
3. Brand not applied: using placeholder logo + wrong fonts + wrong background color

## Architecture

```
Configure -> Monitor -> Explore -> View (greyed until run selected)
```

**Explore tab**: Results table. Click row = inline expand showing FULL run config (signals + all exec config, no collapse). Has "Open in View" button.

**View tab**: Greyed out in nav until a run is selected in Explore. When active, shows:
- Full run config (same as expand, for reference)
- "View Run" button that triggers the actual backtest (visualize endpoint)
- After backtest completes: OHLCV chart with trade markers + trades table

The key UX improvement: clicking a row in Explore is INSTANT (just shows the config data already in the result row). The slow backtest only runs when user explicitly clicks "View Run" in the View tab.

---

## Tasks

### Task 1: Brand foundation -- index.css + logo assets

**Files**: `index.css`, `public/mangrove-logo.svg`, `public/mangrove-mark.svg`

Steps:
1. Copy `branding/Mangrove-Horiz-FullColor-WhiteType.svg` to `experiment_ui/public/mangrove-logo.svg`
2. Copy `branding/Mangrove-M-Full.svg` to `experiment_ui/public/mangrove-mark.svg`
3. Rewrite `index.css`:
   - Background: `#000000` (Rich Black per brand guidelines, NOT #0C0D10)
   - Surface: `#0A0A0A` (near-black for cards)
   - Elevated: `#141414` (slightly lighter)
   - Border: `#1E1E1E` (subtle gray)
   - Font stack: `'Halyard Display', 'Halyard Text', system-ui, sans-serif` for headings
   - Body font: `'Acumin Variable Concept', system-ui, sans-serif`
   - Mono font: `'JetBrains Mono', 'SF Mono', monospace` for data
   - Subheads: UPPERCASE with `letter-spacing: 0.075em` (75% per brand guidelines)
   - Keep all existing utility classes (.card, .input, .btn-primary, etc.) but update colors
   - Color pairing rule: accent colors only appear on black/dark backgrounds, never adjacent to each other

Verify: `npx vite build` succeeds

### Task 2: App.tsx -- real logo + 4-tab nav with View tab

**Files**: `App.tsx`

Steps:
1. Replace the placeholder "M" box with the actual SVG mark (`/mangrove-mark.svg`) as an `<img>` tag, sized to 28x28
2. Replace "MANGROVE" text with the horizontal logo (`/mangrove-logo.svg`) or keep text but use Halyard Display Bold with proper tracking
3. Add "View" as 4th nav tab with conditional styling:
   - No `selectedRun` state: greyed out (`opacity-40 pointer-events-none cursor-default`)
   - Has `selectedRun`: active, navigable
4. Lift `selectedRun` state to App level: `{ experimentId, runIndex, row }` or null
5. Pass `onSelectRun` callback to ExploreView
6. When a run is selected, store it in App state and enable the View tab
7. Add route: `/view` -> `<ViewTab />` component
8. Pass `selectedRun` to ViewTab

Verify: App renders with real logo, 4 tabs visible, View tab greyed out

### Task 3: ExploreView -- simplify expand, remove chart/trades

**Files**: `ExploreView.tsx`

Steps:
1. Remove all chart/trades code: delete OHLCVChart component, TradesTab component, detailTab state, visualizeResult import
2. Remove `detailLoading` / `detail` state -- no more visualize call on row click
3. Row click just toggles expand (instant, no API call)
4. ExpandedDetail shows (from the ResultRow data + entry_json/exit_json parsing):
   - Metrics strip (same as now)
   - Entry Signals section -- parse `entry_json` field from the result row
   - Exit Signals section -- parse `exit_json` field from the result row
   - Execution Config -- ALL params visible, no collapse. Grouped into sections.
   - Provenance line (data file, seed, code version)
   - "Open in View" button (calls `onSelectRun` from props, then navigates to /view)
5. Accept `onSelectRun` prop from App

Verify: Click row = instant expand with full config. No loading spinner. "Open in View" button visible.

### Task 4: ViewTab -- new view with chart + trades

**Files**: `views/ViewTab.tsx` (NEW)

Steps:
1. Create ViewTab component accepting `selectedRun: { experimentId, runIndex, row }` prop
2. Layout:
   - Top: Run summary header (run #, asset, timeframe, trigger, key metrics)
   - Middle: Full run config (same as Explore expand -- signals + exec config)
   - "View Run" button (prominent, brand blue)
   - Below button: empty area that fills with chart + trades after backtest
3. "View Run" button:
   - Calls `visualizeResult(experimentId, runIndex)`
   - Shows loading state ("Running backtest...")
   - On success: renders OHLCV chart + trades table below
4. Move OHLCVChart and TradesTab components here (from ExploreView)
5. Chart: same lightweight-charts v5 implementation (candlestick + volume + trade markers)
6. Trades table: same as before (summary strip + trade rows)

Verify: Navigate to View with a selected run. See config. Click "View Run". Chart + trades appear.

### Task 5: Wire up navigation flow

**Files**: `App.tsx`, `ExploreView.tsx`, `ViewTab.tsx`

Steps:
1. In ExploreView: "Open in View" button sets selectedRun in App state + navigates to /view using `useNavigate()`
2. In App: View tab link becomes active (remove greyed-out styling)
3. In ViewTab: if no selectedRun, show "Select a run from Explore to view details"
4. When user navigates away from View and back, selectedRun persists (it's in App state)
5. If user selects a different run in Explore, it updates the selectedRun and View tab shows the new run

Verify: Full flow: Explore -> click row -> click "Open in View" -> View tab active -> click "View Run" -> chart renders

### Task 6: Build, deploy to container, verify

Steps:
1. `npx vite build --outDir ../experiment_ui_dist`
2. `docker cp experiment_ui_dist/. mangrove-sweep:/app/MarketSimulator/experiment_ui_dist/`
3. Open http://localhost:5100/ in Playwright
4. Verify:
   - Real logo in nav bar
   - Black background
   - 4 tabs (Configure, Monitor, Explore, View)
   - View tab greyed out
   - Explore: click row -> instant expand with full config
   - Click "Open in View" -> View tab activates, navigate to it
   - Click "View Run" -> chart + trades render
   - Check brand colors: blue accent on black, orange badges on black, no color-on-color

---

## What NOT to do

- Don't call visualize endpoint on row click in Explore (that's what caused "Loading detail..." hang)
- Don't put chart/trades in the accordion expand
- Don't use collapsible execution config -- show it all
- Don't use Geist font -- use brand fonts (Halyard/Acumin) with system-ui fallbacks
- Don't use #0C0D10 background -- use #000000 (Rich Black per brand guidelines)
