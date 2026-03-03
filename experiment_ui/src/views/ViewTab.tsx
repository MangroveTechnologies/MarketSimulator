import { useState, useEffect, useRef } from 'react'
import { createChart, CandlestickSeries, HistogramSeries, createSeriesMarkers, type IChartApi } from 'lightweight-charts'
import { getOhlcv, visualizeResult } from '../api/client'
import type { SelectedRun } from '../App'
import type { VisualizeResponse, OHLCVCandle, TradeRecord, SignalInstance } from '../types'

export default function ViewTab({ selectedRun }: { selectedRun: SelectedRun | null }) {
  const [candles, setCandles] = useState<OHLCVCandle[]>([])
  const [candleLoading, setCandleLoading] = useState(false)
  const [vizData, setVizData] = useState<VisualizeResponse | null>(null)
  const [vizLoading, setVizLoading] = useState(false)
  const [error, setError] = useState('')

  // Load OHLCV data immediately when run changes
  useEffect(() => {
    setCandles([])
    setVizData(null)
    setError('')
    if (!selectedRun) return

    setCandleLoading(true)
    getOhlcv(selectedRun.experimentId, selectedRun.runIndex)
      .then(data => setCandles(data.ohlcv))
      .catch(e => setError(e?.message || 'Failed to load OHLCV data'))
      .finally(() => setCandleLoading(false))
  }, [selectedRun?.experimentId, selectedRun?.runIndex])

  if (!selectedRun) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-mg-dim">
        <p className="text-lg font-semibold mb-2">No Run Selected</p>
        <p className="text-sm">Select a run from the Explore tab to view details here.</p>
      </div>
    )
  }

  const { row } = selectedRun

  // When vizData exists, prefer fresh metrics from the re-run over stored Parquet values.
  const m = vizData?.metrics ?? row
  const startBal = (m as any).starting_balance_result || m.ending_balance - ((m as any).net_pnl || 0)
  const returnPct = startBal > 0 ? ((m.ending_balance - startBal) / startBal * 100) : 0

  let entry: SignalInstance[] = []
  let exit: SignalInstance[] = []
  try { entry = JSON.parse(row.entry_json || '[]') } catch {}
  try { exit = JSON.parse(row.exit_json || '[]') } catch {}

  const handleViewRun = async () => {
    setVizLoading(true)
    setError('')
    try {
      const data = await visualizeResult(selectedRun.experimentId, selectedRun.runIndex)
      if (data.viz_error) setError(data.viz_error)
      setVizData(data)
    } catch (e: any) {
      setError(e?.message || 'Failed to run backtest')
    } finally {
      setVizLoading(false)
    }
  }

  const metricItems = [
    { label: 'Sharpe', val: fmtNum(m.sharpe_ratio, 2) },
    { label: 'Sortino', val: fmtNum(m.sortino_ratio, 2) },
    { label: 'Calmar', val: fmtNum(m.calmar_ratio, 2) },
    { label: 'Return', val: `${returnPct.toFixed(1)}%`, color: returnPct >= 0 ? 'text-mg-blue' : 'text-mg-red' },
    { label: 'Max DD', val: `${fmtNum(m.max_drawdown, 2)}%` },
    { label: 'DD Dur', val: `${m.max_drawdown_duration ?? '-'}` },
    { label: 'Trades', val: m.total_trades },
    { label: 'Win Rate', val: `${fmtNum(m.win_rate, 1)}%` },
    { label: 'Net PnL', val: `$${fmtNum(m.net_pnl, 2)}`, color: (m.net_pnl || 0) >= 0 ? 'text-mg-blue' : 'text-mg-red' },
    { label: 'Start Bal', val: `$${startBal.toFixed(0)}` },
    { label: 'End Bal', val: `$${fmtNum(m.ending_balance, 0)}` },
  ]

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
    <div className="space-y-5">
      {/* Run header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="subhead text-lg text-mg-dim">
            Run #{row.run_index} -- {row.asset} {row.timeframe}
          </h1>
          <p className="text-sm text-mg-muted mt-1">
            {row.trigger_name} | {m.total_trades} trades | {row.data_file_path}
          </p>
        </div>
        <button
          onClick={handleViewRun}
          disabled={vizLoading}
          className="btn-primary text-sm px-6 py-2.5"
        >
          {vizLoading ? 'Running Backtest...' : vizData ? 'Re-run Backtest' : 'View Run'}
        </button>
      </div>

      {/* Metrics strip */}
      <div className="grid grid-cols-4 sm:grid-cols-6 lg:grid-cols-11 gap-3">
        {metricItems.map(item => (
          <div key={item.label} className="card px-3 py-2.5 text-center">
            <div className={`font-mono text-sm font-bold ${item.color || ''}`}>{item.val}</div>
            <div className="subhead text-[9px] text-mg-dim mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* OHLCV Chart -- loads immediately from data file */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 row-border flex items-center justify-between">
          <h4 className="subhead text-[11px] text-mg-dim">
            OHLCV Chart -- {row.asset} {row.timeframe}
          </h4>
          {vizData && vizData.trades.length > 0 && (
            <span className="text-[10px] text-mg-blue font-mono">{vizData.trades.length} trade markers shown</span>
          )}
        </div>
        <div className="p-3">
          {candleLoading ? (
            <div className="h-[480px] flex items-center justify-center text-mg-dim text-sm">Loading chart data...</div>
          ) : candles.length > 0 ? (
            <OHLCVChart candles={candles} trades={vizData?.trades ?? []} />
          ) : (
            <div className="h-[480px] flex items-center justify-center text-mg-dim text-sm">
              {error || 'No chart data available'}
            </div>
          )}
        </div>
      </div>

      {/* Signals + Config */}
      <div className="card p-4">
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

        {/* Execution config */}
        <div className="mt-4 pt-3 border-t border-subtle">
          <h4 className="subhead text-[11px] text-mg-dim mb-2">Execution Config</h4>
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-3">
            {execFields.map(([k, v]) => (
              <div key={k} className="bg-mg-elevated rounded border border-mg-border px-3 py-2">
                <div className="font-mono text-xs font-bold">{fmtConfigVal(v)}</div>
                <div className="text-[9px] text-mg-dim">{k}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Full execution config from visualize (if available) */}
        {vizData?.strategy_config?.execution_config && (
          <div className="mt-3 pt-3 border-t border-subtle">
            <h4 className="subhead text-[11px] text-mg-dim mb-2">
              Full Execution Config ({Object.keys(vizData.strategy_config.execution_config).length} params)
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
              {Object.entries(vizData.strategy_config.execution_config).map(([k, v]) => (
                <div key={k} className="flex items-baseline gap-2 text-xs">
                  <span className="text-mg-dim truncate">{k}:</span>
                  <span className="font-mono font-medium">{fmtConfigVal(v)}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Provenance */}
        <div className="mt-3 pt-3 border-t border-subtle text-xs text-mg-muted flex gap-4">
          <span>data: {row.data_file_path}</span>
          <span>seed: {row.rng_seed}</span>
          <span>code: {row.code_version || 'n/a'}</span>
        </div>
      </div>

      {/* Error */}
      {error && !candleLoading && candles.length > 0 && (
        <div className="card p-4 border-mg-red text-mg-red text-sm">
          {error}
        </div>
      )}

      {/* Trades table (only after View Run) */}
      {vizData && vizData.trades.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 row-border">
            <h4 className="subhead text-[11px] text-mg-dim">Trade History</h4>
          </div>
          <TradesTable trades={vizData.trades} />
        </div>
      )}

      {/* Loading state for backtest */}
      {vizLoading && (
        <div className="card p-8 text-center text-mg-dim">
          <p className="text-sm font-medium mb-1">Running backtest...</p>
          <p className="text-xs">Re-executing strategy to generate trade data</p>
        </div>
      )}
    </div>
  )
}

// -- OHLCV Chart ---------------------------------------------------------------

function OHLCVChart({ candles, trades }: { candles: OHLCVCandle[]; trades: TradeRecord[] }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light'
    const bg = isDark ? '#000000' : '#F5F6F8'
    const textColor = isDark ? '#8B8FA3' : '#6B7280'
    const gridColor = isDark ? '#141414' : '#E8E9EB'

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 480,
      layout: { background: { color: bg }, textColor, fontFamily: "'JetBrains Mono', monospace", fontSize: 11 },
      grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
      crosshair: { mode: 0 },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: gridColor },
      rightPriceScale: { borderColor: gridColor },
    })
    chartRef.current = chart

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#42A7C6',
      downColor: '#FF4713',
      borderUpColor: '#42A7C6',
      borderDownColor: '#FF4713',
      wickUpColor: '#42A7C680',
      wickDownColor: '#FF471380',
    })
    candleSeries.setData(candles as any)

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    })
    chart.priceScale('vol').applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    })
    volumeSeries.setData(
      candles.map(c => ({
        time: c.time as any,
        value: c.volume,
        color: c.close >= c.open ? '#42A7C620' : '#FF471320',
      }))
    )

    // Add trade markers if we have them
    if (trades.length > 0) {
      const markers: any[] = []
      for (const t of trades) {
        if (t.entry_timestamp) {
          markers.push({
            time: Math.floor(new Date(t.entry_timestamp).getTime() / 1000),
            position: 'belowBar',
            color: '#42A7C6',
            shape: 'arrowUp',
            text: 'BUY',
          })
        }
        if (t.exit_timestamp) {
          markers.push({
            time: Math.floor(new Date(t.exit_timestamp).getTime() / 1000),
            position: 'aboveBar',
            color: t.profit_loss >= 0 ? '#42A7C6' : '#FF4713',
            shape: 'arrowDown',
            text: t.exit_reason || 'EXIT',
          })
        }
      }
      markers.sort((a, b) => a.time - b.time)
      createSeriesMarkers(candleSeries, markers)
    }

    chart.timeScale().fitContent()

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [candles, trades])

  return <div ref={containerRef} className="w-full" />
}

// -- Trades table ---------------------------------------------------------------

function TradesTable({ trades }: { trades: TradeRecord[] }) {
  const wins = trades.filter(t => t.profit_loss >= 0).length
  const losses = trades.length - wins
  const totalPnl = trades.reduce((s, t) => s + t.profit_loss, 0)
  const avgPnl = totalPnl / trades.length

  return (
    <div>
      <div className="flex gap-4 px-4 py-2 text-xs row-border">
        <span className="text-mg-dim">{trades.length} trades</span>
        <span className="text-mg-blue">{wins}W</span>
        <span className="text-mg-red">{losses}L</span>
        <span className={totalPnl >= 0 ? 'text-mg-blue' : 'text-mg-red'}>
          Total: ${totalPnl.toFixed(2)}
        </span>
        <span className="text-mg-dim">Avg: ${avgPnl.toFixed(2)}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              {['#', 'Entry', 'Exit', 'Size', 'Entry $', 'Exit $', 'SL', 'TP', 'P&L', 'Balance', 'Reason'].map(h => (
                <th key={h} className="text-left px-3 py-2 subhead text-[10px] text-mg-dim row-border">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="row-border-subtle hover:bg-mg-hover transition-colors">
                <td className="px-3 py-2 font-mono text-mg-dim">{i + 1}</td>
                <td className="px-3 py-2 font-mono text-mg-dim whitespace-nowrap">{fmtTimestamp(t.entry_timestamp)}</td>
                <td className="px-3 py-2 font-mono text-mg-dim whitespace-nowrap">{fmtTimestamp(t.exit_timestamp)}</td>
                <td className="px-3 py-2 font-mono">{t.position_size.toFixed(4)}</td>
                <td className="px-3 py-2 font-mono">${t.entry_price.toFixed(2)}</td>
                <td className="px-3 py-2 font-mono">${t.exit_price.toFixed(2)}</td>
                <td className="px-3 py-2 font-mono text-mg-dim">{t.stop_loss_price ? `$${t.stop_loss_price.toFixed(2)}` : '-'}</td>
                <td className="px-3 py-2 font-mono text-mg-dim">{t.take_profit_price ? `$${t.take_profit_price.toFixed(2)}` : '-'}</td>
                <td className={`px-3 py-2 font-mono font-semibold ${t.profit_loss >= 0 ? 'text-mg-blue' : 'text-mg-red'}`}>
                  {t.profit_loss >= 0 ? '+' : ''}{t.profit_loss.toFixed(2)}
                </td>
                <td className="px-3 py-2 font-mono">${t.ending_balance.toFixed(0)}</td>
                <td className="px-3 py-2">
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                    t.exit_reason === 'TP' ? 'bg-blue-15 text-mg-blue' :
                    t.exit_reason === 'SL' ? 'bg-red-15 text-mg-red' :
                    'bg-mg-elevated text-mg-dim'
                  }`}>
                    {t.exit_reason || '-'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// -- Helpers -------------------------------------------------------------------

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

function fmtTimestamp(ts: string | null): string {
  if (!ts) return '-'
  const d = new Date(ts)
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()} ${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`
}
