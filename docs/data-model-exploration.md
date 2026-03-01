# Data Model Exploration: Strategy Object to Parquet

## Part A: A Complete Strategy Config Object

This is what the backtest engine receives. It's ONE object -- signals, their
params, and execution config all together.

### Example 1: Simple (1 trigger + 1 filter)

```json
{
  "name": "sweep_BTC_ema_cross_up_rsi_oversold",
  "asset": "BTC",
  "entry": [
    {
      "name": "ema_cross_up",
      "signal_type": "TRIGGER",
      "timeframe": "1d",
      "params": {
        "window_fast": 9,
        "window_slow": 21
      }
    },
    {
      "name": "rsi_oversold",
      "signal_type": "FILTER",
      "timeframe": "1d",
      "params": {
        "window": 14,
        "threshold": 30
      }
    }
  ],
  "exit": [],
  "reward_factor": 2.0,
  "execution_config": {
    "max_risk_per_trade": 0.01,
    "stop_loss_calculation": "dynamic_atr",
    "atr_period": 14,
    "atr_volatility_factor": 2.0,
    "atr_short_weight": 0.7,
    "atr_long_weight": 0.3,
    "initial_balance": 10000,
    "min_balance_threshold": 0.1,
    "min_trade_amount": 25,
    "max_open_positions": 1,
    "max_trades_per_day": 5,
    "max_units_per_trade": 10000,
    "max_trade_amount": 10000000,
    "volatility_window": 24,
    "target_volatility": 0.02,
    "volatility_mode": "stddev",
    "enable_volatility_adjustment": false,
    "max_hold_time_hours": null,
    "cooldown_bars": 2,
    "daily_momentum_limit": 3,
    "weekly_momentum_limit": 3,
    "max_hold_bars": 100,
    "exit_on_loss_after_bars": 50,
    "exit_on_profit_after_bars": 100,
    "profit_threshold_pct": 0.04,
    "slippage_pct": 0.0075,
    "fee_pct": 0.0085
  }
}
```

### Example 2: Multi-filter (1 trigger + 3 filters, v2)

```json
{
  "name": "sweep_SOL_macd_bullish_cross_3f",
  "asset": "SOL",
  "entry": [
    {
      "name": "macd_bullish_cross",
      "signal_type": "TRIGGER",
      "timeframe": "5m",
      "params": {
        "window_fast": 12,
        "window_slow": 26,
        "window_sign": 9
      }
    },
    {
      "name": "adx_strong_trend",
      "signal_type": "FILTER",
      "timeframe": "5m",
      "params": {
        "window": 14,
        "threshold": 25
      }
    },
    {
      "name": "rsi_oversold",
      "signal_type": "FILTER",
      "timeframe": "5m",
      "params": {
        "window": 14,
        "threshold": 35
      }
    },
    {
      "name": "vwap_above",
      "signal_type": "FILTER",
      "timeframe": "5m",
      "params": {
        "window": 20
      }
    }
  ],
  "exit": [],
  "reward_factor": 3.0,
  "execution_config": {
    "max_risk_per_trade": 0.02,
    "stop_loss_calculation": "dynamic_atr",
    "atr_period": 21,
    "atr_volatility_factor": 1.5,
    "atr_short_weight": 0.7,
    "atr_long_weight": 0.3,
    "initial_balance": 10000,
    "min_balance_threshold": 0.1,
    "min_trade_amount": 25,
    "max_open_positions": 3,
    "max_trades_per_day": 10,
    "max_units_per_trade": 10000,
    "max_trade_amount": 10000000,
    "volatility_window": 20,
    "target_volatility": 0.01,
    "volatility_mode": "stddev",
    "enable_volatility_adjustment": true,
    "max_hold_time_hours": null,
    "cooldown_bars": 1,
    "daily_momentum_limit": 3,
    "weekly_momentum_limit": 3,
    "max_hold_bars": 200,
    "exit_on_loss_after_bars": 100,
    "exit_on_profit_after_bars": 200,
    "profit_threshold_pct": 0.08,
    "slippage_pct": 0.005,
    "fee_pct": 0.005
  }
}
```

### The variable parts

Both `entry` and `exit` are variable-length arrays of variable-schema objects.
Example 1 has 2 entry signals, Example 2 has 4. Signal params differ by
signal (ema_cross_up has window_fast/window_slow, rsi_oversold has
window/threshold, vwap_above has just window). Exit signals follow the same
structure and will be used for exit signal sweeping in future experiments.

---

## Part B: How This Maps to Parquet

### Design principle: one row = one backtest run

No redundancy. Every column serves exactly one purpose. The strategy config
is stored as parts that can be reassembled, not as a monolithic blob duplicated
alongside extracted columns.

### The Parquet schema

```
BACKTEST RESULT ROW
===================

--- Experiment identity ---
experiment_id           TEXT        "exp_20260228_v2_full"
run_index               INT32       42917

--- Provenance ---
code_version            TEXT        "a1b2c3d"
rng_seed                INT32       42
data_file_path          TEXT        "btc_2022-08-01_2026-02-15_1d.csv"
data_file_hash          TEXT        "sha256:e3b0c44298fc..."
data_file_rows          INT32       1298

--- Strategy identity (reconstructable) ---
strategy_name           TEXT        "sweep_BTC_ema_cross_up_rsi_oversold"
asset                   TEXT        "BTC"
timeframe               TEXT        "1d"
start_date              DATE        2022-08-01
end_date                DATE        2026-02-15

--- Entry signals (variable part, stored as JSON) ---
entry_json              TEXT        '[{"name":"ema_cross_up","signal_type":"TRIGGER","timeframe":"1d","params":{"window_fast":9,"window_slow":21}},{"name":"rsi_oversold","signal_type":"FILTER","timeframe":"1d","params":{"window":14,"threshold":30}}]'
trigger_name            TEXT        "ema_cross_up"
num_entry_signals       INT16       2

--- Exit signals (variable part, stored as JSON -- same structure as entry) ---
exit_json               TEXT        '[]'
num_exit_signals        INT16       0

--- Execution config (fixed schema, all flat columns) ---
reward_factor           FLOAT32     2.0
max_risk_per_trade      FLOAT32     0.01
stop_loss_calculation   TEXT        "dynamic_atr"
atr_period              INT16       14
atr_volatility_factor   FLOAT32     2.0
atr_short_weight        FLOAT32     0.7
atr_long_weight         FLOAT32     0.3
initial_balance         FLOAT32     10000.0
min_balance_threshold   FLOAT32     0.1
min_trade_amount        FLOAT32     25.0
max_open_positions      INT16       1
max_trades_per_day      INT16       5
max_units_per_trade     FLOAT32     10000.0
max_trade_amount        FLOAT32     10000000.0
volatility_window       INT16       24
target_volatility       FLOAT32     0.02
volatility_mode         TEXT        "stddev"
enable_volatility_adj   BOOLEAN     false
max_hold_time_hours     INT16       null
cooldown_bars           INT16       2
daily_momentum_limit    FLOAT32     3.0
weekly_momentum_limit   FLOAT32     3.0
max_hold_bars           INT16       100
exit_on_loss_after_bars INT16       50
exit_on_profit_after_bars INT16     100
profit_threshold_pct    FLOAT32     0.04
slippage_pct            FLOAT32     0.0075
fee_pct                 FLOAT32     0.0085

--- Backtest results (fixed schema, all flat columns) ---
total_trades            INT32       35
win_rate                FLOAT32     0.6857
total_return            FLOAT32     226.7376
sharpe_ratio            FLOAT64     4.4489
sortino_ratio           FLOAT64     5.5692
max_drawdown            FLOAT64     7.6751
max_drawdown_duration   INT32       12
calmar_ratio            FLOAT64     29.5421
gain_to_pain_ratio      FLOAT64     3.2
irr_annualized          FLOAT64     180.5
irr_daily               FLOAT64     0.00234
avg_daily_return        FLOAT64     0.00198
max_consecutive_wins    INT16       8
max_consecutive_losses  INT16       3
num_days                INT32       1294
net_pnl                 FLOAT64     3416.59
starting_balance        FLOAT64     10000.0
ending_balance          FLOAT64     13416.59

--- Run metadata ---
status                  TEXT        "ok"
error_msg               TEXT        null
elapsed_seconds         FLOAT32     4.75
completed_at            TEXT        "2026-02-28T05:41:03Z"
```

### What's queryable without JSON parsing

Everything except the individual signal params. These queries all hit native
columns and are fast:

```sql
-- Top strategies by Sharpe for BTC with aggressive risk
SELECT * FROM read_parquet('results/**/*.parquet')
WHERE asset = 'BTC'
  AND max_risk_per_trade = 0.02
  AND reward_factor >= 3.0
  AND status = 'ok'
ORDER BY sharpe_ratio DESC
LIMIT 50

-- Compare reward_factor impact on returns
SELECT reward_factor, AVG(total_return), AVG(sharpe_ratio), COUNT(*)
FROM read_parquet('results/**/*.parquet')
WHERE status = 'ok' AND total_trades >= 10
GROUP BY reward_factor
ORDER BY reward_factor

-- Which triggers work best with tight stops?
SELECT trigger_name, AVG(sharpe_ratio), COUNT(*)
FROM read_parquet('results/**/*.parquet')
WHERE atr_volatility_factor <= 1.5 AND status = 'ok'
GROUP BY trigger_name
ORDER BY AVG(sharpe_ratio) DESC
```

### What requires JSON parsing (still works, just slower)

Queries on specific signal params:

```sql
-- Find strategies where RSI threshold was set to 25
SELECT * FROM read_parquet('results/**/*.parquet')
WHERE entry_json LIKE '%"threshold": 25%'

-- Or with DuckDB JSON extraction (exact but parses per row)
SELECT * FROM read_parquet('results/**/*.parquet')
WHERE json_extract(entry_json, '$[1].params.threshold')::INT = 25
```

### Reconstructing the full strategy config

No blob stored. Reconstruct from parts:

```python
strategy_config = {
    "name": row["strategy_name"],
    "asset": row["asset"],
    "entry": json.loads(row["entry_json"]),
    "exit": json.loads(row["exit_json"]),
    "reward_factor": row["reward_factor"],
    "execution_config": {
        "max_risk_per_trade": row["max_risk_per_trade"],
        "stop_loss_calculation": row["stop_loss_calculation"],
        "atr_period": row["atr_period"],
        # ... all 28 exec config columns ...
    }
}
```

This reconstruction is lossless. The flat columns + entry_json + exit_json
contain everything needed to reproduce the exact strategy config that was run.

### File layout on disk (and in GCS bucket)

```
MarketSimulator/data/experiments/
  exp_20260228_v2_full/
    metadata.json                    Experiment config, provenance, status
    results/
      BTC/
        worker_00_chunk_000.parquet
        worker_00_chunk_001.parquet
        worker_01_chunk_000.parquet
      ETH/
        worker_02_chunk_000.parquet
        ...
      SOL/
        ...
```

DuckDB queries the whole experiment:
```sql
SELECT * FROM read_parquet('data/experiments/exp_20260228_v2_full/results/**/*.parquet')
```

Or just one symbol (partition pruning):
```sql
SELECT * FROM read_parquet('data/experiments/exp_20260228_v2_full/results/BTC/*.parquet')
```

The entire directory structure syncs to a GCS bucket as-is. DuckDB can also
read directly from GCS:
```sql
SELECT * FROM read_parquet('gs://bucket/experiments/exp_*/results/**/*.parquet')
```

### Column count summary

| Section | Columns | Storage |
|---------|---------|---------|
| Experiment identity | 2 | ~40 bytes |
| Provenance | 5 | ~120 bytes |
| Strategy identity | 5 | ~60 bytes |
| Entry/exit signals | 3 | ~200-800 bytes (JSON, variable) |
| Execution config | 28 | ~100 bytes |
| Backtest results | 18 | ~120 bytes |
| Run metadata | 4 | ~60 bytes |
| **Total** | **65** | **~700-1400 bytes/row** |

At 1M rows: ~700MB-1.4GB uncompressed. Parquet typically compresses 5-10x
for this kind of data, so ~100-250MB on disk.
