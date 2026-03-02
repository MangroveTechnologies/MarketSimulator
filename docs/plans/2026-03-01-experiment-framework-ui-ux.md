# Experiment Framework -- UI/UX Design Document

Date: 2026-03-01
Status: Draft
Author: Tim Darrah + Claude
Depends on:
- [Requirements](./2026-02-28-experiment-framework-requirements.md)
- [Specification](./2026-02-28-experiment-framework-specification.md)
- [Architecture](./2026-02-28-experiment-framework-architecture.md)
- [Mangrove Brand Guidelines](../../branding/brand-guidelines.md)

## 1. Design Direction

The experiment framework dashboard follows the Mangrove brand identity
adapted for a data-heavy research tool. The aesthetic is **utilitarian
precision** -- clean, dense, information-rich. Not flashy, not minimal.
Every pixel communicates data or enables interaction.

### Brand Integration

| Element | Brand Specification | Implementation |
|---------|-------------------|----------------|
| Primary background | Rich Black #000000 | Dark mode default: #0C0D10 (softened black) |
| Accent blue (primary interactive) | Pantone 7702 #42A7C6 | Buttons, toggles, selected states, links |
| Accent blue (secondary) | Pantone 630 #74C3D5 | Hover states, secondary badges |
| Accent orange (alerts) | Pantone 172 #FF4713 | Error states, warnings, danger actions |
| Accent warm (highlights) | Pantone 1375 #FF9E18 | FILTER signal badges, active counts |
| Logo | Horizontal primary (white type) | Top-left of navigation bar |
| Light mode bg | #F5F6F8 | Light mode surfaces |

### Typography

| Use | Font | Fallback | Weight |
|-----|------|----------|--------|
| Page titles | Halyard Display | system-ui | Bold (700) |
| Section headers | Halyard Text | system-ui | Medium (500), uppercase, 0.75em letter-spacing |
| Body / controls | Acumin Variable | -apple-system, 'Segoe UI', sans-serif | Regular (400) |
| Monospace (values, code) | JetBrains Mono | 'SF Mono', 'Fira Code', monospace | Regular (400) |
| Fallback (if Adobe fonts unavailable) | Inter | system-ui | Variable |

Note: Halyard and Acumin are Adobe Fonts (paid). The React build should
load them via Adobe Fonts kit. Fallback to Inter (Google Fonts) for
environments without Adobe access.

### Color Rules (from brand guidelines)

- Color on black: YES (accent colors on dark backgrounds)
- Black on color: YES (dark text on colored surfaces)
- Color on color: NEVER (do not pair accent colors with each other)
- TRIGGER badge: #42A7C6 (blue) on dark background
- FILTER badge: #FF9E18 (orange) on dark background
- Never use blue + orange adjacent without a dark separator

## 2. Color System (CSS Variables)

### Dark Mode (default)

```css
:root[data-theme="dark"] {
  /* Surfaces */
  --bg-primary: #0C0D10;
  --bg-surface: #16171D;
  --bg-elevated: #1E2028;
  --bg-hover: #252730;
  --border: #2E3140;

  /* Text */
  --text-primary: #E8EAF0;
  --text-secondary: #8B8FA3;
  --text-muted: #5C6070;

  /* Brand accents */
  --accent-blue: #42A7C6;
  --accent-blue-light: #74C3D5;
  --accent-blue-hover: #5AB8D4;
  --accent-orange: #FF9E18;
  --accent-red: #FF4713;

  /* Semantic */
  --success: #42A7C6;
  --warning: #FF9E18;
  --error: #FF4713;
  --info: #74C3D5;

  /* Interactive */
  --btn-primary-bg: #42A7C6;
  --btn-primary-text: #000000;
  --btn-secondary-bg: #1E2028;
  --btn-secondary-border: #2E3140;
  --toggle-on: #42A7C6;
  --toggle-off: #3A3D4A;
}
```

### Light Mode

```css
:root[data-theme="light"] {
  --bg-primary: #F5F6F8;
  --bg-surface: #FFFFFF;
  --bg-elevated: #F0F1F3;
  --bg-hover: #E8E9EB;
  --border: #D1D5DB;

  --text-primary: #1F2937;
  --text-secondary: #6B7280;
  --text-muted: #9CA3AF;

  --accent-blue: #337D95;
  --accent-blue-light: #42A7C6;
  --accent-blue-hover: #2B6678;
  --accent-orange: #D97706;
  --accent-red: #DC2626;

  --success: #337D95;
  --warning: #D97706;
  --error: #DC2626;
  --info: #42A7C6;

  --btn-primary-bg: #42A7C6;
  --btn-primary-text: #FFFFFF;
  --btn-secondary-bg: #FFFFFF;
  --btn-secondary-border: #D1D5DB;
  --toggle-on: #42A7C6;
  --toggle-off: #D1D5DB;
}
```

## 3. Tailwind Configuration

```javascript
// tailwind.config.ts
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        mangrove: {
          blue: { DEFAULT: '#42A7C6', light: '#74C3D5', dark: '#337D95' },
          orange: { DEFAULT: '#FF9E18', dark: '#D97706' },
          red: { DEFAULT: '#FF4713', dark: '#DC2626' },
        },
        surface: {
          primary: 'var(--bg-primary)',
          card: 'var(--bg-surface)',
          elevated: 'var(--bg-elevated)',
          hover: 'var(--bg-hover)',
        },
      },
      fontFamily: {
        display: ['Halyard Display', 'Inter', 'system-ui', 'sans-serif'],
        heading: ['Halyard Text', 'Inter', 'system-ui', 'sans-serif'],
        body: ['Acumin Variable Concept', 'Inter', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'SF Mono', 'Fira Code', 'monospace'],
      },
    },
  },
}
```

## 4. Component Design System

### 4.1 Collapsible Section

The primary container for all configuration groups.

```
+-----------------------------------------------------------+
| [v] SECTION TITLE                          [2 selected]   |
+-----------------------------------------------------------+
|                                                           |
|  Section content here. Padding 16px.                      |
|  Background: var(--bg-surface)                            |
|                                                           |
+-----------------------------------------------------------+
```

- Header: `var(--bg-surface)`, font-heading uppercase, 0.75em letter-spacing
- Hover: `var(--bg-hover)`
- Badge: pill shape, `var(--accent-blue)` bg, black text
- Chevron: rotates -90deg when collapsed
- Border: 1px `var(--border)`, radius 8px
- Body: hidden when collapsed, 16px padding

### 4.2 Dataset Selector

Multi-select table with search, sort, and checkbox column.

```
+-----------------------------------------------------------+
| [ Search datasets...                              ]       |
+-----------------------------------------------------------+
| [x] | ASSET | TIMEFRAME | START      | END        | ROWS |
|-----|-------|-----------|------------|------------|------|
| [x] | BTC   | 1d        | 2022-08-01 | 2026-02-15 | 1294 |
| [x] | ETH   | 4h        | 2024-01-01 | 2026-02-01 | 4572 |
| [ ] | DOGE  | 5m        | 2021-04-01 | 2021-06-15 |21327 |
+-----------------------------------------------------------+
```

- Header row: uppercase, `var(--text-secondary)`, sortable (click toggles asc/desc)
- Selected rows: subtle left border 2px `var(--accent-blue)`
- Hover: `var(--bg-hover)`
- Checkbox: accent-color `var(--accent-blue)`
- Monospace values: `font-mono` for dates and numbers
- Row count right-aligned

### 4.3 Signal Badge

```
[TRIGGER]  -- bg: var(--accent-blue), text: #000
[FILTER]   -- bg: var(--accent-orange), text: #000
```

- Font: 0.65rem, uppercase, font-heading, 600 weight
- Padding: 2px 8px
- Border-radius: 4px

### 4.4 Sweep Toggle

Custom toggle switch for enabling parameter sweeps.

```
OFF:  [  O     ]  gray track, white knob left
ON:   [     O  ]  blue track, white knob right
```

- Track: 40x22px, border-radius 11px
- Knob: 18x18px circle, white, 2px from edge
- ON color: `var(--accent-blue)`
- OFF color: `var(--toggle-off)`
- Transition: 200ms ease

### 4.5 Param Grid Builder

Inline controls for sweep parameter definition.

```
+-------------------------------------------------------+
| window_fast  int  [min: 5 ] [max: 30] [step: 5]  [5-30] |
| window_slow  int  [min: 20] [max:100] [step:10]  [20-100]|
+-------------------------------------------------------+
```

- Background: `var(--bg-primary)` (one level deeper than section)
- Border: 1px `var(--border)`, radius 6px
- Param name: `font-mono`, 500 weight
- Type label: `var(--text-muted)`, 0.7rem
- Range hint: `var(--text-muted)`, right-aligned
- Number inputs: 65px width, `var(--bg-elevated)` background

### 4.6 Stats Bar

Summary of the current experiment configuration.

```
+-----------------------------------------------------------+
|  7        34        62        48        3        23,856   |
| datasets  triggers  filters  configs  params/sig  TOTAL  |
+-----------------------------------------------------------+
```

- Background: `var(--bg-elevated)`
- Border-radius: 8px
- Values: `font-mono`, 1.3rem, `var(--accent-blue)` color
- Total: larger (1.5rem), bolder
- Labels: uppercase, 0.7rem, `var(--text-muted)`
- Layout: flex, center-aligned, gap 24px

### 4.7 Buttons

```
[ Validate ]  -- secondary: surface bg, border, text
[ Launch ]    -- primary: accent-blue bg, black text
```

- Primary: `var(--btn-primary-bg)`, `var(--btn-primary-text)`, hover opacity 0.9
- Secondary: `var(--btn-secondary-bg)`, border `var(--btn-secondary-border)`
- Padding: 10px 24px
- Border-radius: 8px
- Font: 600 weight, 0.85rem
- Disabled: 50% opacity, cursor not-allowed

## 5. View Layouts

### 5.1 Navigation

Top bar with logo left, view tabs center, theme toggle right.

```
+-----------------------------------------------------------+
| [M] Mangrove    [Configure] [Monitor] [Explore]    [D/L] |
+-----------------------------------------------------------+
```

- Height: 56px
- Background: `var(--bg-surface)`
- Border-bottom: 1px `var(--border)`
- Logo: Mangrove-M-Full.svg + "Mangrove" text
- Active tab: `var(--accent-blue)` bottom border 2px
- Inactive tab: `var(--text-secondary)`
- Theme toggle: icon button (sun/moon)

### 5.2 Configure View

Single scrollable page with collapsible sections. Stats bar sticky at bottom.

```
+-----------------------------------------------------------+
| NAV BAR                                                    |
+-----------------------------------------------------------+
|                                                           |
| [v] Experiment Name                                       |
|     Name: [________________]  Desc: [________________]    |
|                                                           |
| [v] Datasets                              [7 selected]   |
|     (table with search, sort, checkboxes)                 |
|                                                           |
| [v] Search Mode & Signal Config                           |
|     (o) Random  ( ) Grid                                  |
|     N per dataset: [10000]                                |
|     Entry triggers: [1]  Min filters: [1]  Max: [3]      |
|     Exit triggers: [0-1]  Exit filters: [0-3]            |
|     Param combos/signal: [3]                              |
|                                                           |
| [v] Execution Config                   [3 swept | 48 configs]
|     (table with sweep toggles and param builders)         |
|                                                           |
+-----------------------------------------------------------+
| STATS BAR (sticky)                                        |
| 7 datasets | 34 triggers | 62 filters | 48 configs | ... |
+-----------------------------------------------------------+
| [ Validate ]  [ Launch Experiment ]                       |
+-----------------------------------------------------------+
```

### 5.3 Monitor View

Experiment list + selected experiment progress.

```
+-----------------------------------------------------------+
| NAV BAR                                                    |
+-----------------------------------------------------------+
| EXPERIMENTS                                                |
| +-------------------------------------------------------+ |
| | Name              | Status  | Runs      | Created     | |
| | exec_sweep_v2     | RUNNING | 186K/300K | 2026-02-28  | |
| | smoke_test        | DONE    | 10/10     | 2026-03-01  | |
| +-------------------------------------------------------+ |
|                                                           |
| PROGRESS: exec_sweep_v2                                   |
| Overall [=================>        ] 62%                  |
| Rate: 0.85/s  ETA: 37h  Elapsed: 61h                     |
|                                                           |
| BTC/1d  [==========================] 100%  DONE           |
| ETH/4h  [==================>       ]  72%  running        |
| DOGE/5m [=============>            ]  54%  running        |
|                                                           |
| Errors: 0    No-trade: 41,203 (22.2%)                    |
| [ Pause ] [ Cancel ]                                      |
+-----------------------------------------------------------+
```

### 5.4 Explore View

Results table + detail panel.

```
+-----------------------------------------------------------+
| NAV BAR                                                    |
+-----------------------------------------------------------+
| Experiment: [exec_sweep_v2  v]                            |
|                                                           |
| FILTERS                                                    |
| Dataset: [All v] Trigger: [All v] Status: [ok v]         |
| Min trades: [10]  reward_factor: [All v]                  |
|                                                           |
| Sort: [sharpe_ratio v] [DESC v]  Showing 1-50 of 12,847  |
| +-------------------------------------------------------+ |
| | # | trigger    | filters     | rf  | sharpe | trades  | |
| | 1 | pvo_bull_x | nvi_bearish | 3.0 | 5.89   | 17      | |
| | 2 | pvo_bear_x | nvi_bearish | 2.0 | 5.87   | 18      | |
| +-------------------------------------------------------+ |
|                                                           |
| DETAIL: run_index 42917                                    |
| Sharpe: 5.89  Return: 184%  Drawdown: 0.51%  Trades: 17  |
| [Chart] [Trades]                                          |
|                                                           |
| (Chart: OHLCV candles + entry/exit markers + signals)     |
| (Trades: entry/exit price, P&L, exit reason, bars held)   |
+-----------------------------------------------------------+
```

## 6. React Component Tree

```
App
  ThemeProvider
    NavBar
    Routes
      ConfigureView
        CollapsibleSection (x6)
          ExperimentNameSection
          DatasetSelector
          SearchModeSection
            SignalCountControls
            RandomBudgetInput (random mode only)
          ExecConfigEditor
            SweepToggle (per param)
            ParamGridBuilder (expanded when toggled)
        StatsBar
        ActionButtons (Validate, Launch, Save Template)
      MonitorView
        ExperimentList
        ProgressPanel
          ProgressBar (overall)
          DatasetProgressBars
          PauseResumeControls
      ExploreView
        ExperimentSelector
        FilterBar
        ResultsTable
        BacktestDetail
          MetricsSummary
          ChartView (lightweight-charts)
          TradesTable
```

## 7. Tech Stack (React Upgrade)

| Technology | Version | Purpose |
|-----------|---------|---------|
| React | 18+ | UI framework |
| TypeScript | 5+ | Type safety |
| Vite | 6+ | Build tool |
| React Router | 6+ | Client-side routing |
| Tailwind CSS | 3+ | Utility-first styling |
| Headless UI | 2+ | Accessible unstyled components |
| Heroicons | 2+ | Icon set |
| lightweight-charts | 4+ | OHLCV candlestick charts |
| Axios | 1+ | HTTP client |
| TanStack Query | 5+ | Data fetching + caching |

## 8. Responsive Behavior

| Breakpoint | Layout |
|-----------|--------|
| >= 1200px | Full layout, side-by-side panels where applicable |
| 768-1199px | Stacked layout, full-width sections |
| < 768px | Mobile: stacked, collapsible sections default closed |

The dashboard is primarily a desktop tool. Mobile support is a nice-to-have
for monitoring, not a primary design target.

## 9. Interaction Patterns

- **Collapsible sections**: Click header to toggle. Chevron rotates. Content animates height.
- **Sweep toggles**: Click to enable/disable. When enabled, param builder slides open below.
- **Dataset selection**: Checkbox per row. Select-all in header. Badge updates live.
- **Search mode switch**: Click card to select. Controls update immediately.
- **Stats bar**: Updates on every configuration change. Shows live cross-product count.
- **Validate**: Creates experiment on server, computes exact run count, shows result.
- **Launch**: Starts workers, redirects to Monitor view with the new experiment selected.
- **Theme toggle**: Instant switch, persisted in localStorage.

## 10. Logo Assets for MarketSimulator

Copy these from MangroveMarkets to MarketSimulator:

```
MarketSimulator/
  public/
    Mangrove-Horiz-FullColor-WhiteType.svg   (dark mode nav)
    Mangrove-Horiz-FullColor.svg             (light mode nav)
    Mangrove-M-Full.svg                      (favicon, compact)
```

Source: `MangroveMarkets/branding/`
