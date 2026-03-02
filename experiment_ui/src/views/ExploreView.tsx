import { useState, useEffect, useCallback } from 'react'
import { listExperiments, queryResults, visualizeResult } from '../api/client'
import type { ExperimentSummary, ResultRow, VisualizeResponse } from '../types'

const RESULT_COLUMNS: { key: string; label: string; fmt?: (v: any, row?: ResultRow) => string; sortable?: boolean }[] = [
  { key: 'run_index', label: 'Run #', sortable: true },
  { key: 'asset', label: 'Asset' },
  { key: 'timeframe', label: 'Timeframe' },
  { key: 'start_date', label: 'Start' },
  { key: 'end_date', label: 'End' },
  { key: 'num_days', label: 'Days', sortable: true },
  { key: 'total_trades', label: 'Trades', sortable: true },
  { key: 'win_rate', label: 'Win Rate', sortable: true, fmt: v => v != null ? `${v.toFixed(1)}%` : '-' },
  { key: '_return', label: 'Return', sortable: false, fmt: (_v, row) => {
    if (!row) return '-'
    const s = row.starting_balance_result || (row.ending_balance - (row.net_pnl || 0))
    return s > 0 ? `${(((row.ending_balance - s) / s) * 100).toFixed(2)}%` : '0%'
  }},
  { key: 'sharpe_ratio', label: 'Sharpe', sortable: true, fmt: v => v != null ? v.toFixed(2) : '-' },
  { key: 'sortino_ratio', label: 'Sortino', sortable: true, fmt: v => v != null ? v.toFixed(2) : '-' },
  { key: 'max_drawdown', label: 'Max DD', sortable: true, fmt: v => v != null ? `${v.toFixed(2)}%` : '-' },
  { key: 'calmar_ratio', label: 'Calmar', sortable: true, fmt: v => v != null ? v.toFixed(2) : '-' },
  { key: 'net_pnl', label: 'Net PnL', sortable: true, fmt: v => v != null ? `$${v.toFixed(2)}` : '-' },
  { key: 'starting_balance_result', label: 'Start Bal', fmt: v => v != null ? `$${v.toFixed(0)}` : '-' },
  { key: 'ending_balance', label: 'End Bal', sortable: true, fmt: v => v != null ? `$${v.toFixed(2)}` : '-' },
  { key: 'status', label: 'Status' },
]

export default function ExploreView() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [selectedExp, setSelectedExp] = useState('')
  const [results, setResults] = useState<ResultRow[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [sort, setSort] = useState('sharpe_ratio')
  const [order, setOrder] = useState<'asc' | 'desc'>('desc')
  const [filters, setFilters] = useState({ status: 'ok', min_trades: '0', min_sharpe: '', asset: '' })
  const [detail, setDetail] = useState<VisualizeResponse | null>(null)
  const [detailTab, setDetailTab] = useState<'config' | 'trades'>('config')
  const [loading, setLoading] = useState(false)
  const limit = 50

  useEffect(() => {
    listExperiments().then(exps => {
      setExperiments(exps)
      const nonDraft = exps.filter(e => e.status !== 'draft')
      if (nonDraft.length > 0) setSelectedExp(nonDraft[0].experiment_id)
    })
  }, [])

  const loadResults = useCallback(async () => {
    if (!selectedExp) return
    setLoading(true)
    try {
      const params: Record<string, any> = { sort, order, limit, offset }
      if (filters.status) params.status = filters.status
      if (filters.asset) params.asset = filters.asset
      if (Number(filters.min_trades) > 0) params.min_trades = filters.min_trades
      if (filters.min_sharpe) params.min_sharpe = filters.min_sharpe
      const data = await queryResults(selectedExp, params)
      setResults(data.results)
      setTotal(data.total)
    } catch (e: any) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [selectedExp, sort, order, offset, filters])

  useEffect(() => { loadResults() }, [loadResults])

  const handleSort = (col: string) => {
    if (sort === col) setOrder(o => o === 'desc' ? 'asc' : 'desc')
    else { setSort(col); setOrder('desc') }
    setOffset(0)
  }

  const handleDetail = async (runIndex: number) => {
    if (!selectedExp) return
    try {
      const data = await visualizeResult(selectedExp, runIndex)
      setDetail(data)
      setDetailTab('config')
    } catch (e) { console.error(e) }
  }

  const currentPage = Math.floor(offset / limit) + 1
  const totalPages = Math.ceil(total / limit)

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Experiment Explorer</h1>

      {/* Experiment selector */}
      <div className="mb-4">
        <label className="text-xs text-mg-dim uppercase tracking-wider block mb-1">Experiment</label>
        <select
          value={selectedExp}
          onChange={e => { setSelectedExp(e.target.value); setOffset(0); setDetail(null) }}
          className="bg-mg-elevated border border-mg-border rounded-lg px-3 py-2 text-sm min-w-[400px] text-mg-text"
        >
          {experiments.map(e => (
            <option key={e.experiment_id} value={e.experiment_id}>
              {e.name} ({e.status}, {e.total_runs ?? '?'} runs)
            </option>
          ))}
        </select>
      </div>

      {/* Filters */}
      <div className="flex gap-3 items-end flex-wrap p-3 bg-mg-surface border border-mg-border rounded-lg mb-4">
        <div>
          <label className="text-xs text-mg-dim block mb-1">Status</label>
          <select value={filters.status} onChange={e => setFilters(f => ({ ...f, status: e.target.value }))}
            className="bg-mg-elevated border border-mg-border rounded px-2 py-1.5 text-sm text-mg-text">
            <option value="">All</option>
            <option value="ok">ok</option>
            <option value="no_trades">no_trades</option>
            <option value="error">error</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-mg-dim block mb-1">Asset</label>
          <input value={filters.asset} onChange={e => setFilters(f => ({ ...f, asset: e.target.value }))}
            placeholder="e.g. BTC" className="bg-mg-elevated border border-mg-border rounded px-2 py-1.5 text-sm w-20 text-mg-text" />
        </div>
        <div>
          <label className="text-xs text-mg-dim block mb-1">Min Trades</label>
          <input type="number" value={filters.min_trades} onChange={e => setFilters(f => ({ ...f, min_trades: e.target.value }))}
            className="bg-mg-elevated border border-mg-border rounded px-2 py-1.5 text-sm w-20 text-mg-text" />
        </div>
        <div>
          <label className="text-xs text-mg-dim block mb-1">Min Sharpe</label>
          <input type="number" step="0.1" value={filters.min_sharpe} onChange={e => setFilters(f => ({ ...f, min_sharpe: e.target.value }))}
            className="bg-mg-elevated border border-mg-border rounded px-2 py-1.5 text-sm w-20 text-mg-text" />
        </div>
        <button onClick={() => { setOffset(0); loadResults() }}
          className="px-4 py-1.5 bg-mg-blue text-mg-black text-sm font-semibold rounded hover:opacity-90 transition">
          Search
        </button>
      </div>

      {/* Results info */}
      <div className="flex justify-between text-xs text-mg-dim mb-2">
        <span>Showing {offset + 1}-{Math.min(offset + limit, total)} of {total.toLocaleString()} results</span>
        <span>Sorted by {sort} {order}</span>
      </div>

      {/* Results table */}
      <div className="overflow-x-auto border border-mg-border rounded-lg bg-mg-surface">
        <table className="w-full text-sm">
          <thead>
            <tr>
              {RESULT_COLUMNS.map(col => (
                <th
                  key={col.key}
                  onClick={() => col.sortable !== false && col.key[0] !== '_' && handleSort(col.key)}
                  className={`text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider border-b border-mg-border whitespace-nowrap
                    ${col.sortable !== false && col.key[0] !== '_' ? 'cursor-pointer hover:text-mg-blue' : ''}
                    ${sort === col.key ? 'text-mg-blue' : 'text-mg-dim'}`}
                >
                  {col.label}{sort === col.key ? (order === 'desc' ? ' \u25BC' : ' \u25B2') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={RESULT_COLUMNS.length} className="text-center py-8 text-mg-dim">Loading...</td></tr>
            ) : results.length === 0 ? (
              <tr><td colSpan={RESULT_COLUMNS.length} className="text-center py-8 text-mg-dim">No results found</td></tr>
            ) : results.map(row => (
              <tr
                key={row.run_index}
                onClick={() => handleDetail(row.run_index)}
                className={`cursor-pointer border-b border-mg-border/50 hover:bg-mg-hover transition-colors
                  ${detail?.run_index === row.run_index ? 'bg-mg-blue/5 border-l-2 border-l-mg-blue' : ''}`}
              >
                {RESULT_COLUMNS.map(col => {
                  const val = col.key === '_return' ? null : (row as any)[col.key]
                  const display = col.fmt ? col.fmt(val, row) : (val ?? '-')
                  const isNum = ['net_pnl', 'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'total_return'].includes(col.key)
                  const isPositive = col.key === 'net_pnl' && val > 0
                  const isNegative = col.key === 'net_pnl' && val < 0
                  return (
                    <td key={col.key} className={`px-3 py-2 whitespace-nowrap ${isNum ? 'font-mono text-xs' : 'text-sm'}
                      ${isPositive ? 'text-mg-blue' : ''} ${isNegative ? 'text-mg-red' : ''}`}>
                      {String(display)}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="flex gap-3 justify-center items-center mt-4">
        <button disabled={currentPage <= 1} onClick={() => setOffset(Math.max(0, offset - limit))}
          className="px-3 py-1.5 text-sm border border-mg-border rounded bg-mg-surface text-mg-text disabled:opacity-30">
          Prev
        </button>
        <span className="text-xs text-mg-dim">Page {currentPage} of {totalPages}</span>
        <button disabled={currentPage >= totalPages} onClick={() => setOffset(offset + limit)}
          className="px-3 py-1.5 text-sm border border-mg-border rounded bg-mg-surface text-mg-text disabled:opacity-30">
          Next
        </button>
      </div>

      {/* Detail panel */}
      {detail && (
        <DetailPanel detail={detail} activeTab={detailTab} onTabChange={setDetailTab} />
      )}
    </div>
  )
}

function DetailPanel({ detail, activeTab, onTabChange }: {
  detail: VisualizeResponse
  activeTab: 'config' | 'trades'
  onTabChange: (t: 'config' | 'trades') => void
}) {
  const sc = detail.strategy_config
  const m = detail.metrics
  const prov = detail.provenance
  const ec = sc.execution_config || {}
  const startBal = m.ending_balance - (m.net_pnl || 0)
  const returnPct = startBal > 0 ? ((m.ending_balance - startBal) / startBal * 100) : 0

  const metrics = [
    { label: 'Sharpe', val: m.sharpe_ratio?.toFixed(2) },
    { label: 'Sortino', val: m.sortino_ratio?.toFixed(2) },
    { label: 'Return', val: `${returnPct.toFixed(2)}%` },
    { label: 'Max Drawdown', val: `${(m.max_drawdown || 0).toFixed(2)}%` },
    { label: 'Calmar', val: m.calmar_ratio?.toFixed(2) },
    { label: 'Trades', val: m.total_trades },
    { label: 'Win Rate', val: `${(m.win_rate || 0).toFixed(1)}%` },
    { label: 'Net PnL', val: `$${(m.net_pnl || 0).toFixed(2)}` },
    { label: 'Start Balance', val: `$${startBal.toFixed(2)}` },
    { label: 'End Balance', val: `$${(m.ending_balance || 0).toFixed(2)}` },
  ]

  return (
    <div className="mt-6 border border-mg-border rounded-lg bg-mg-surface overflow-hidden">
      <div className="px-4 py-3 border-b border-mg-border flex justify-between items-center">
        <h3 className="font-semibold text-sm">
          Run #{detail.run_index} -- {sc.asset} {sc.name}
        </h3>
        <div className="flex gap-1">
          {(['config', 'trades'] as const).map(tab => (
            <button key={tab} onClick={() => onTabChange(tab)}
              className={`px-3 py-1 text-xs font-medium rounded ${
                activeTab === tab ? 'bg-mg-blue text-mg-black' : 'text-mg-dim hover:text-mg-text'
              }`}>
              {tab === 'config' ? 'Configuration' : 'Trades'}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4">
        {activeTab === 'config' ? (
          <>
            {/* Metrics grid */}
            <SectionLabel>Results</SectionLabel>
            <div className="grid grid-cols-5 gap-3 mb-6">
              {metrics.map(m => (
                <div key={m.label} className="bg-mg-elevated rounded-lg p-3 text-center">
                  <div className="font-mono text-lg font-bold">{m.val}</div>
                  <div className="text-[10px] text-mg-dim uppercase tracking-wider mt-0.5">{m.label}</div>
                </div>
              ))}
            </div>

            {/* Entry Signals */}
            <SectionLabel>Entry Signals ({sc.entry.length})</SectionLabel>
            <div className="space-y-2 mb-6">
              {sc.entry.map((sig, i) => <SignalCard key={i} signal={sig} />)}
            </div>

            {/* Exit Signals */}
            <SectionLabel>Exit Signals ({sc.exit.length})</SectionLabel>
            <div className="space-y-2 mb-6">
              {sc.exit.length === 0 ? (
                <p className="text-sm text-mg-dim">None (using SL/TP from execution config)</p>
              ) : sc.exit.map((sig, i) => <SignalCard key={i} signal={sig} />)}
            </div>

            {/* Execution Config */}
            <details className="mb-4">
              <summary className="cursor-pointer text-xs font-semibold text-mg-dim uppercase tracking-wider mb-2">
                Execution Config ({Object.keys(ec).length} params)
              </summary>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      <th className="text-left px-2 py-1.5 text-mg-dim font-semibold uppercase border-b border-mg-border">Parameter</th>
                      <th className="text-left px-2 py-1.5 text-mg-dim font-semibold uppercase border-b border-mg-border">Value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(ec).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => (
                      <tr key={k} className="border-b border-mg-border/30">
                        <td className="px-2 py-1 font-mono text-mg-dim">{k}</td>
                        <td className="px-2 py-1 font-mono">{v === null ? 'null' : typeof v === 'boolean' ? (v ? 'true' : 'false') : String(Math.round(Number(v) * 10000) / 10000)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>

            {/* Provenance */}
            <details>
              <summary className="cursor-pointer text-xs font-semibold text-mg-dim uppercase tracking-wider mb-2">
                Provenance
              </summary>
              <table className="text-xs">
                <tbody>
                  {[
                    ['Data file', prov.data_file_path],
                    ['File hash', prov.data_file_hash || '(not computed)'],
                    ['RNG seed', String(prov.rng_seed)],
                    ['Code version', prov.code_version || '(not set)'],
                  ].map(([label, val]) => (
                    <tr key={label}>
                      <td className="pr-4 py-0.5 text-mg-dim">{label}</td>
                      <td className="font-mono">{val}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          </>
        ) : (
          <div className="text-sm text-mg-dim text-center py-8">
            Trade visualization coming soon. Re-run the backtest to see individual trades and OHLCV chart.
          </div>
        )}
      </div>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h4 className="text-xs font-semibold text-mg-dim uppercase tracking-wider mb-2">{children}</h4>
}

function SignalCard({ signal }: { signal: { name: string; signal_type: string; timeframe: string; params: Record<string, any> } }) {
  const isTrigger = signal.signal_type === 'TRIGGER'
  return (
    <div className="bg-mg-elevated rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1">
        <span className={`text-[10px] font-bold uppercase px-1.5 py-0.5 rounded ${
          isTrigger ? 'bg-mg-blue text-mg-black' : 'bg-mg-orange text-mg-black'
        }`}>
          {signal.signal_type}
        </span>
        <span className="font-semibold text-sm">{signal.name}</span>
        <span className="text-xs text-mg-dim font-mono">timeframe: {signal.timeframe}</span>
      </div>
      {Object.keys(signal.params).length > 0 && (
        <div className="mt-1 pl-2 border-l-2 border-mg-border">
          {Object.entries(signal.params).map(([k, v]) => (
            <div key={k} className="flex gap-3 text-xs">
              <span className="text-mg-dim w-28">{k}</span>
              <span className="font-mono">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
