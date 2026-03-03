import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { listExperiments, queryResults } from '../api/client'
import type { ExperimentSummary, ResultRow, SignalInstance } from '../types'
import type { SelectedRun } from '../App'

// ── Column definitions ───────────────────────────────────────────

const COLUMNS: { key: string; label: string; mono?: boolean; sortable?: boolean; fmt?: (v: any, row?: ResultRow) => string }[] = [
  { key: 'run_index', label: '#', mono: true, sortable: true },
  { key: 'asset', label: 'Asset' },
  { key: 'timeframe', label: 'TF' },
  { key: 'trigger_name', label: 'Trigger' },
  { key: '_filters', label: 'Filters', fmt: (_v, row) => {
    if (!row?.entry_json) return '-'
    try {
      const sigs = JSON.parse(row.entry_json)
      const filters = sigs.filter((s: any) => s.signal_type === 'FILTER').map((s: any) => s.name)
      return filters.length ? filters.join(', ') : '-'
    } catch { return '-' }
  }},
  { key: 'total_trades', label: 'Trades', mono: true, sortable: true },
  { key: 'win_rate', label: 'Win%', mono: true, sortable: true, fmt: v => v != null ? `${v.toFixed(1)}%` : '-' },
  { key: 'sharpe_ratio', label: 'Sharpe', mono: true, sortable: true, fmt: v => v != null ? v.toFixed(2) : '-' },
  { key: 'sortino_ratio', label: 'Sortino', mono: true, sortable: true, fmt: v => v != null ? v.toFixed(2) : '-' },
  { key: 'calmar_ratio', label: 'Calmar', mono: true, sortable: true, fmt: v => v != null ? v.toFixed(2) : '-' },
  { key: 'max_drawdown', label: 'Max DD', mono: true, sortable: true, fmt: v => v != null ? `${v.toFixed(2)}%` : '-' },
  { key: 'max_drawdown_duration', label: 'DD Dur', mono: true, sortable: true, fmt: v => v != null ? `${v}` : '-' },
  { key: 'starting_balance_result', label: 'Start Bal', mono: true, fmt: v => v != null ? `$${Number(v).toFixed(0)}` : '-' },
  { key: 'ending_balance', label: 'End Bal', mono: true, sortable: true, fmt: v => v != null ? `$${Number(v).toFixed(0)}` : '-' },
  { key: 'status', label: 'Status' },
]

const PAGE_SIZES = [50, 100, 200, 500]

// ── Main view ────────────────────────────────────────────────────

export default function ExploreView({ onSelectRun }: { onSelectRun: (run: SelectedRun) => void }) {
  const navigate = useNavigate()
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [selectedExp, setSelectedExp] = useState('')
  const [results, setResults] = useState<ResultRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('sharpe_ratio')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [filters, setFilters] = useState({ status: 'ok', min_trades: '5', min_sharpe: '', asset: '', trigger: '' })
  const [expandedRun, setExpandedRun] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [limit, setLimit] = useState(100)

  useEffect(() => {
    listExperiments().then(exps => {
      setExperiments(exps)
      const active = exps.filter(e => e.status !== 'draft')
      if (active.length > 0) setSelectedExp(active[0].experiment_id)
    })
  }, [])

  const loadResults = useCallback(async () => {
    if (!selectedExp) return
    setLoading(true)
    try {
      const params: Record<string, any> = { sort, order, limit, offset }
      if (filters.status) params.status = filters.status
      if (filters.asset) params.asset = filters.asset
      if (filters.trigger) params.trigger_name = filters.trigger
      if (Number(filters.min_trades) > 0) params.min_trades = filters.min_trades
      if (filters.min_sharpe) params.min_sharpe = filters.min_sharpe
      const data = await queryResults(selectedExp, params)
      setResults(data.results)
      setTotal(data.total)
    } catch (e) {
      console.error('Failed to load results:', e)
    } finally {
      setLoading(false)
    }
  }, [selectedExp, sort, order, offset, limit, filters])

  useEffect(() => { loadResults() }, [loadResults])

  const handleSort = (col: string) => {
    if (sort === col) setOrder(o => o === 'desc' ? 'asc' : 'desc')
    else { setSort(col); setOrder('desc') }
    setOffset(0)
  }

  const handleRowClick = (runIndex: number) => {
    setExpandedRun(expandedRun === runIndex ? null : runIndex)
  }

  const handleOpenInView = (row: ResultRow) => {
    onSelectRun({ experimentId: selectedExp, runIndex: row.run_index, row })
    navigate('/view')
  }

  const handlePageSizeChange = (newLimit: number) => {
    setLimit(newLimit)
    setOffset(0)
  }

  const currentPage = Math.floor(offset / limit) + 1
  const totalPages = Math.ceil(total / limit)

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h1 className="subhead text-lg text-mg-dim">Explore Results</h1>
        <div className="flex items-center gap-3">
          <label className="subhead text-[10px] text-mg-muted">Experiment</label>
          <select
            value={selectedExp}
            onChange={e => { setSelectedExp(e.target.value); setOffset(0); setExpandedRun(null) }}
            className="input min-w-[320px]"
          >
            {experiments.map(e => (
              <option key={e.experiment_id} value={e.experiment_id}>
                {e.name} -- {e.status} ({e.total_runs?.toLocaleString() ?? '?'} runs)
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Filter bar */}
      <div className="card p-4">
        <div className="flex gap-4 items-end flex-wrap">
          <FilterField label="Status">
            <select value={filters.status} onChange={e => { setFilters(f => ({ ...f, status: e.target.value })); setOffset(0) }}
              className="input">
              <option value="">All</option>
              <option value="ok">ok</option>
              <option value="no_trades">no_trades</option>
              <option value="error">error</option>
            </select>
          </FilterField>
          <FilterField label="Asset">
            <input value={filters.asset} onChange={e => setFilters(f => ({ ...f, asset: e.target.value }))}
              placeholder="BTC" className="input w-20" />
          </FilterField>
          <FilterField label="Trigger">
            <input value={filters.trigger} onChange={e => setFilters(f => ({ ...f, trigger: e.target.value }))}
              placeholder="e.g. rsi" className="input w-28" />
          </FilterField>
          <FilterField label="Min Trades">
            <input type="number" value={filters.min_trades} onChange={e => setFilters(f => ({ ...f, min_trades: e.target.value }))}
              className="input w-20" />
          </FilterField>
          <FilterField label="Min Sharpe">
            <input type="number" step="0.1" value={filters.min_sharpe} onChange={e => setFilters(f => ({ ...f, min_sharpe: e.target.value }))}
              className="input w-20" />
          </FilterField>
          <button onClick={() => { setOffset(0); loadResults() }} className="btn-primary">Search</button>
        </div>
      </div>

      {/* Results info */}
      <div className="flex justify-between text-xs text-mg-dim px-1">
        <span>{total.toLocaleString()} results {filters.status && `(${filters.status})`}</span>
        <span className="font-mono">Page {currentPage} / {totalPages} -- sorted by {sort} {order}</span>
      </div>

      {/* Results table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-mg-elevated">
                {COLUMNS.map(col => (
                  <th
                    key={col.key}
                    onClick={() => col.sortable && col.key[0] !== '_' && handleSort(col.key)}
                    className={`text-left px-3 py-2.5 subhead text-[10px] whitespace-nowrap row-border
                      ${col.sortable && col.key[0] !== '_' ? 'cursor-pointer hover:text-mg-blue select-none' : ''}
                      ${sort === col.key ? 'text-mg-blue' : 'text-mg-dim'}`}
                  >
                    {col.label}
                    {sort === col.key && (order === 'desc' ? ' \u25BC' : ' \u25B2')}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr><td colSpan={COLUMNS.length} className="text-center py-12 text-mg-dim">Loading...</td></tr>
              ) : results.length === 0 ? (
                <tr><td colSpan={COLUMNS.length} className="text-center py-12 text-mg-dim">No results found</td></tr>
              ) : results.map(row => (
                <ResultRowGroup
                  key={row.run_index}
                  row={row}
                  isExpanded={expandedRun === row.run_index}
                  onClick={() => handleRowClick(row.run_index)}
                  onOpenInView={() => handleOpenInView(row)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      <div className="flex gap-3 justify-center items-center mt-4">
        <button disabled={currentPage <= 1} onClick={() => setOffset(Math.max(0, offset - limit))}
          className="btn-secondary disabled:opacity-30">Prev</button>
        <span className="text-xs text-mg-dim font-mono">{currentPage} / {totalPages}</span>
        <button disabled={currentPage >= totalPages} onClick={() => setOffset(offset + limit)}
          className="btn-secondary disabled:opacity-30">Next</button>
        <select
          value={limit}
          onChange={e => handlePageSizeChange(Number(e.target.value))}
          className="input text-xs ml-3"
        >
          {PAGE_SIZES.map(size => (
            <option key={size} value={size}>{size} / page</option>
          ))}
        </select>
      </div>
    </div>
  )
}

// ── Result row + inline expand ───────────────────────────────────

function ResultRowGroup({ row, isExpanded, onClick, onOpenInView }: {
  row: ResultRow
  isExpanded: boolean
  onClick: () => void
  onOpenInView: () => void
}) {
  const pnlColor = row.net_pnl > 0 ? 'text-mg-blue' : row.net_pnl < 0 ? 'text-mg-red' : ''

  return (
    <>
      <tr
        onClick={onClick}
        className={`cursor-pointer row-border-subtle transition-colors
          ${isExpanded ? 'bg-mg-elevated' : 'hover:bg-mg-hover'}`}
      >
        {COLUMNS.map(col => {
          const raw = col.key[0] === '_' ? null : (row as any)[col.key]
          const display = col.fmt ? col.fmt(raw, row) : (raw ?? '-')
          const isPnl = col.key === 'net_pnl'
          return (
            <td key={col.key} className={`px-3 py-2 whitespace-nowrap
              ${col.mono ? 'font-mono text-xs' : 'text-sm'}
              ${isPnl ? pnlColor : ''}
              ${col.key === 'status' ? statusClass(row.status) : ''}`}>
              {String(display)}
            </td>
          )
        })}
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={COLUMNS.length} className="p-0 bg-mg-bg">
            <div className="border-l-2 border-mg-blue mx-2 my-1">
              <ExpandedDetail row={row} onOpenInView={onOpenInView} />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

function statusClass(status: string): string {
  switch (status) {
    case 'ok': return 'text-mg-blue'
    case 'no_trades': return 'text-mg-muted'
    case 'error': return 'text-mg-red'
    default: return 'text-mg-dim'
  }
}

// ── Expanded detail panel (instant, no API call) ────────────────

function ExpandedDetail({ row, onOpenInView }: { row: ResultRow; onOpenInView: () => void }) {
  const startBal = row.starting_balance_result || (row.ending_balance - (row.net_pnl || 0))
  const returnPct = startBal > 0 ? ((row.ending_balance - startBal) / startBal * 100) : 0

  // Parse signal configs from JSON
  let entry: SignalInstance[] = []
  let exit: SignalInstance[] = []
  try { entry = JSON.parse(row.entry_json || '[]') } catch {}
  try { exit = JSON.parse(row.exit_json || '[]') } catch {}

  const metricItems = [
    { label: 'Sharpe', val: fmtNum(row.sharpe_ratio, 2) },
    { label: 'Sortino', val: fmtNum(row.sortino_ratio, 2) },
    { label: 'Calmar', val: fmtNum(row.calmar_ratio, 2) },
    { label: 'Return', val: `${returnPct.toFixed(1)}%`, color: returnPct >= 0 ? 'text-mg-blue' : 'text-mg-red' },
    { label: 'Max DD', val: `${fmtNum(row.max_drawdown, 2)}%` },
    { label: 'Trades', val: row.total_trades },
    { label: 'Win Rate', val: `${fmtNum(row.win_rate, 1)}%` },
    { label: 'Net PnL', val: `$${fmtNum(row.net_pnl, 2)}`, color: (row.net_pnl || 0) >= 0 ? 'text-mg-blue' : 'text-mg-red' },
    { label: 'Start Bal', val: `$${startBal.toFixed(0)}` },
    { label: 'End Bal', val: `$${fmtNum(row.ending_balance, 0)}` },
  ]

  // Execution config fields from the Parquet row -- show all non-null values
  const EXEC_KEYS = [
    'reward_factor', 'max_risk_per_trade', 'cooldown_bars', 'atr_period',
    'atr_volatility_factor', 'atr_short_weight', 'atr_long_weight',
    'stop_loss_calculation', 'initial_balance', 'min_balance_threshold',
    'min_trade_amount', 'max_open_positions', 'max_trades_per_day',
    'max_units_per_trade', 'max_trade_amount', 'volatility_window',
    'target_volatility', 'volatility_mode', 'enable_volatility_adj',
    'max_hold_time_hours', 'daily_momentum_limit', 'weekly_momentum_limit',
    'max_hold_bars', 'exit_on_loss_after_bars', 'exit_on_profit_after_bars',
    'profit_threshold_pct', 'slippage_pct', 'fee_pct',
  ]
  const execFields: [string, any][] = EXEC_KEYS
    .map(k => [k, (row as any)[k]] as [string, any])
    .filter(([, v]) => v != null)

  return (
    <div className="p-4 space-y-4">
      {/* Metrics strip */}
      <div className="grid grid-cols-5 lg:grid-cols-10 gap-3">
        {metricItems.map(item => (
          <div key={item.label} className="bg-mg-surface rounded px-2 py-2 text-center border border-mg-border">
            <div className={`font-mono text-sm font-bold ${item.color || ''}`}>{item.val}</div>
            <div className="subhead text-[9px] text-mg-dim mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Signals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <h4 className="subhead text-[11px] text-mg-dim mb-2">Entry Signals ({entry.length})</h4>
          <div className="flex gap-2 flex-wrap">
            {entry.map((sig, i) => <SignalCard key={i} signal={sig} />)}
          </div>
        </div>
        <div>
          <h4 className="subhead text-[11px] text-mg-dim mb-2">Exit Signals ({exit.length})</h4>
          {exit.length === 0 ? (
            <p className="text-xs text-mg-dim">None (SL/TP from execution config)</p>
          ) : (
            <div className="flex gap-2 flex-wrap">
              {exit.map((sig, i) => <SignalCard key={i} signal={sig} />)}
            </div>
          )}
        </div>
      </div>

      {/* Execution config (all visible, no collapse) */}
      <div>
        <h4 className="subhead text-[11px] text-mg-dim mb-2">Execution Config</h4>
        <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
          {execFields.map(([k, v]) => (
            <div key={k} className="bg-mg-surface rounded border border-mg-border px-3 py-2">
              <div className="font-mono text-xs font-bold">{fmtConfigVal(v)}</div>
              <div className="text-[9px] text-mg-dim">{k}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Provenance + View button */}
      <div className="flex items-center justify-between pt-2 border-t border-subtle">
        <div className="text-xs text-mg-muted flex gap-4">
          <span>data: {row.data_file_path}</span>
          <span>seed: {row.rng_seed}</span>
          <span>code: {row.code_version || 'n/a'}</span>
        </div>
        <button onClick={onOpenInView} className="btn-primary text-xs">
          Open in View
        </button>
      </div>
    </div>
  )
}

// ── Shared components ────────────────────────────────────────────

function SignalCard({ signal }: { signal: SignalInstance }) {
  const isTrigger = signal.signal_type === 'TRIGGER'
  return (
    <div className="card-elevated p-3 min-w-[200px]">
      <div className="flex items-center gap-2 mb-1">
        <span className={isTrigger ? 'badge-trigger' : 'badge-filter'}>
          {signal.signal_type}
        </span>
        <span className="font-semibold text-sm">{signal.name}</span>
      </div>
      {Object.keys(signal.params).length > 0 && (
        <div className="mt-1.5 pl-2 border-l-2 border-mg-border">
          {Object.entries(signal.params).map(([k, v]) => (
            <div key={k} className="flex gap-3 text-xs">
              <span className="text-mg-dim w-24 shrink-0">{k}</span>
              <span className="font-mono">{fmtConfigVal(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function FilterField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="subhead text-[10px] text-mg-dim block mb-1">{label}</label>
      {children}
    </div>
  )
}

// ── Utilities ────────────────────────────────────────────────────

function fmtNum(v: any, decimals: number): string {
  if (v == null) return '-'
  return Number(v).toFixed(decimals)
}

function fmtConfigVal(v: any): string {
  if (v === null || v === undefined) return 'null'
  if (typeof v === 'boolean') return v ? 'true' : 'false'
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  return String(v)
}
