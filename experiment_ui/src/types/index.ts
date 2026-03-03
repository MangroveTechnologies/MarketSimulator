// Core types for the experiment framework

export interface Dataset {
  asset: string
  timeframe: string
  file: string
  hash: string
  rows: number
  start_date: string
  end_date: string
}

export interface SignalParam {
  type: string
  min: number | null
  max: number | null
  default: number | string | boolean | null
  optional: boolean
  description: string
}

export interface Signal {
  name: string
  type: 'TRIGGER' | 'FILTER'
  params: Record<string, SignalParam>
  constraints: string[][]
  description: string
  requires: string[]
}

export interface ExperimentSummary {
  experiment_id: string
  name: string
  status: string
  total_runs: number | null
  search_mode: string
  created_at: string
}

export interface ResultRow {
  run_index: number
  experiment_id: string
  asset: string
  timeframe: string
  start_date: string
  end_date: string
  trigger_name: string
  entry_json: string
  exit_json: string
  num_entry_signals: number
  num_exit_signals: number
  total_trades: number
  win_rate: number
  total_return: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  max_drawdown_duration: number
  calmar_ratio: number
  gain_to_pain_ratio: number
  irr_annualized: number
  net_pnl: number
  starting_balance_result: number
  ending_balance: number
  num_days: number
  status: string
  error_msg: string | null
  elapsed_seconds: number
  reward_factor: number
  max_risk_per_trade: number
  cooldown_bars: number
  atr_period: number
  atr_volatility_factor: number
  data_file_path: string
  data_file_hash: string
  data_file_rows: number
  code_version: string
  rng_seed: number
}

export interface ResultsResponse {
  total: number
  offset: number
  limit: number
  results: ResultRow[]
}

export interface OHLCVCandle {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface TradeRecord {
  trade_id: string
  outcome: string
  profit_loss: number
  side: string
  entry_price: number
  exit_price: number
  position_size: number
  beginning_balance: number
  ending_balance: number
  entry_timestamp: string | null
  exit_timestamp: string | null
  exit_reason: string | null
  stop_loss_price: number | null
  take_profit_price: number | null
}

export interface VisualizeResponse {
  run_index: number
  strategy_config: {
    name: string
    asset: string
    entry: SignalInstance[]
    exit: SignalInstance[]
    reward_factor: number
    execution_config: Record<string, any>
  }
  metrics: Record<string, any>
  provenance: {
    data_file_path: string
    data_file_hash: string
    code_version: string
    rng_seed: number
  }
  trades: TradeRecord[]
  ohlcv: OHLCVCandle[]
  viz_error?: string
}

export interface SignalInstance {
  name: string
  signal_type: string
  timeframe: string
  params: Record<string, any>
}
