import { useState, useEffect, useCallback } from 'react'
import { listExperiments, getExperiment, pauseExperiment, launchExperiment } from '../api/client'
import type { ExperimentSummary } from '../types'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-mg-muted',
  validated: 'bg-mg-blue',
  running: 'bg-green-500',
  paused: 'bg-mg-orange',
  completed: 'bg-mg-blue',
  failed: 'bg-mg-red',
}

const STATUS_TEXT: Record<string, string> = {
  draft: 'text-mg-dim',
  validated: 'text-mg-blue',
  running: 'text-green-400',
  paused: 'text-mg-orange',
  completed: 'text-mg-blue',
  failed: 'text-mg-red',
}

interface ExperimentDetail {
  experiment_id: string
  name: string
  description: string
  status: string
  total_runs: number | null
  completed_runs: number
  search_mode: string
  n_random: number | null
  seed: number
  datasets: { asset: string; timeframe: string; file: string; rows: number; start_date: string; end_date: string }[]
  random_signals?: {
    n_entry_triggers: number
    min_entry_filters: number
    max_entry_filters: number
    min_exit_triggers: number
    max_exit_triggers: number
    min_exit_filters: number
    max_exit_filters: number
    n_param_draws: number
  }
  execution_config?: { base: Record<string, any>; sweep_axes: any[] }
  workers_per_dataset: number
  created_at: string
}

export default function MonitorView() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<ExperimentDetail | null>(null)
  const [actionLoading, setActionLoading] = useState(false)

  // Auto-select most recent non-draft experiment
  useEffect(() => {
    const load = async () => {
      const exps = await listExperiments()
      setExperiments(exps)
      if (!selectedId) {
        const active = exps.filter(e => e.status !== 'draft')
        if (active.length > 0) setSelectedId(active[0].experiment_id)
      }
    }
    load()
    const interval = setInterval(load, 10000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const load = async () => {
      const d = await getExperiment(selectedId)
      setDetail(d)
    }
    load()
    const interval = setInterval(load, 5000)
    return () => clearInterval(interval)
  }, [selectedId])

  const handlePause = useCallback(async () => {
    if (!selectedId) return
    setActionLoading(true)
    try {
      await pauseExperiment(selectedId)
      const d = await getExperiment(selectedId)
      setDetail(d)
    } catch (e) { console.error(e) }
    setActionLoading(false)
  }, [selectedId])

  const handleResume = useCallback(async () => {
    if (!selectedId) return
    setActionLoading(true)
    try {
      await launchExperiment(selectedId)
      const d = await getExperiment(selectedId)
      setDetail(d)
    } catch (e) { console.error(e) }
    setActionLoading(false)
  }, [selectedId])

  const pct = detail?.total_runs
    ? Math.min(100, ((detail.completed_runs || 0) / detail.total_runs) * 100)
    : 0

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-wide uppercase text-mg-dim">Experiment Monitor</h1>
        <span className="text-xs text-mg-muted font-mono">
          {experiments.length} experiment{experiments.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Experiment list */}
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr>
              {['Name', 'Status', 'Total Runs', 'Completed', 'Mode', 'Created'].map(h => (
                <th key={h} className="text-left px-3 py-2.5 text-[10px] font-semibold uppercase tracking-wider text-mg-dim border-b border-mg-border">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {experiments.length === 0 && (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-mg-dim text-sm">No experiments found</td></tr>
            )}
            {experiments.map(e => (
              <tr
                key={e.experiment_id}
                onClick={() => setSelectedId(e.experiment_id)}
                className={`cursor-pointer row-border-subtle hover:bg-mg-hover transition-colors
                  ${selectedId === e.experiment_id ? 'bg-blue-5 border-l-2 border-l-mg-blue' : 'border-l-2 border-l-transparent'}`}
              >
                <td className="px-3 py-2 font-medium text-sm">{e.name}</td>
                <td className="px-3 py-2">
                  <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
                    <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[e.status] || 'bg-gray-500'} ${e.status === 'running' ? 'animate-pulse' : ''}`} />
                    <span className={STATUS_TEXT[e.status] || 'text-mg-dim'}>{e.status}</span>
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{e.total_runs?.toLocaleString() ?? '-'}</td>
                <td className="px-3 py-2 font-mono text-xs text-mg-dim">-</td>
                <td className="px-3 py-2 text-xs text-mg-dim">{e.search_mode}</td>
                <td className="px-3 py-2 text-xs text-mg-dim font-mono">{fmtDate(e.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail panel */}
      {detail && (
        <div className="space-y-4">
          {/* Title + description */}
          <div className="card p-4">
            <div className="flex items-start justify-between mb-3">
              <div>
                <h3 className="font-semibold text-lg">{detail.name}</h3>
                {detail.description && (
                  <p className="text-sm text-mg-dim mt-1 max-w-2xl">{detail.description}</p>
                )}
              </div>
              <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-mg-elevated">
                <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[detail.status] || 'bg-gray-500'} ${detail.status === 'running' ? 'animate-pulse' : ''}`} />
                <span className={STATUS_TEXT[detail.status] || 'text-mg-dim'}>{detail.status}</span>
              </span>
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4 mb-4">
              <Stat label="Total Runs" value={detail.total_runs?.toLocaleString() ?? '-'} />
              <Stat label="Completed" value={detail.completed_runs?.toLocaleString() ?? '0'} accent={detail.completed_runs > 0} />
              <Stat label="Remaining" value={detail.total_runs ? (detail.total_runs - (detail.completed_runs || 0)).toLocaleString() : '-'} />
              <Stat label="Progress" value={`${pct.toFixed(1)}%`} accent />
              <Stat label="Mode" value={detail.search_mode} />
              <Stat label="Seed" value={detail.seed?.toString() ?? '-'} />
            </div>

            {/* Progress bar -- always show if total_runs exists */}
            {detail.total_runs != null && detail.total_runs > 0 && (
              <div className="bg-mg-elevated rounded-lg p-3">
                <div className="flex justify-between text-xs text-mg-dim mb-1.5">
                  <span className="font-medium">Overall Progress</span>
                  <span className="font-mono">{(detail.completed_runs || 0).toLocaleString()} / {detail.total_runs.toLocaleString()}</span>
                </div>
                <div className="h-3 bg-mg-border rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      pct >= 100 ? 'bg-mg-blue' : 'bg-gradient-to-r from-mg-blue to-mg-blue-light'
                    }`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                {pct > 0 && pct < 100 && detail.status === 'running' && (
                  <div className="flex justify-between text-[10px] text-mg-muted mt-1">
                    <span>Running...</span>
                    <span>{pct.toFixed(1)}% complete</span>
                  </div>
                )}
              </div>
            )}

            {/* Action buttons */}
            {(detail.status === 'running' || detail.status === 'paused' || detail.status === 'validated') && (
              <div className="flex gap-3 mt-4">
                {detail.status === 'running' && (
                  <button
                    onClick={handlePause}
                    disabled={actionLoading}
                    className="px-4 py-2 text-sm font-medium rounded-lg border border-mg-orange text-mg-orange hover:bg-orange-10 transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Pausing...' : 'Pause'}
                  </button>
                )}
                {(detail.status === 'paused' || detail.status === 'validated') && (
                  <button
                    onClick={handleResume}
                    disabled={actionLoading}
                    className="px-4 py-2 text-sm font-medium rounded-lg bg-mg-blue text-black hover:opacity-90 transition-colors disabled:opacity-50"
                  >
                    {actionLoading ? 'Launching...' : detail.status === 'paused' ? 'Resume' : 'Launch'}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Datasets breakdown */}
          {detail.datasets && detail.datasets.length > 0 && (
            <div className="card overflow-hidden">
              <div className="px-3 py-2.5 row-border">
                <h4 className="text-[10px] font-semibold uppercase tracking-wider text-mg-dim">Datasets ({detail.datasets.length})</h4>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    {['Asset', 'Timeframe', 'Start', 'End', 'Rows', 'Runs/Dataset'].map(h => (
                      <th key={h} className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-mg-dim border-b border-mg-border">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.datasets.map((ds, i) => (
                    <tr key={i} className="row-border-subtle">
                      <td className="px-3 py-2 font-semibold text-sm">{ds.asset}</td>
                      <td className="px-3 py-2 font-mono text-xs">{ds.timeframe}</td>
                      <td className="px-3 py-2 font-mono text-xs text-mg-dim">{ds.start_date}</td>
                      <td className="px-3 py-2 font-mono text-xs text-mg-dim">{ds.end_date}</td>
                      <td className="px-3 py-2 font-mono text-xs">{ds.rows.toLocaleString()}</td>
                      <td className="px-3 py-2 font-mono text-xs text-mg-dim">
                        {detail.n_random?.toLocaleString() ?? '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Config summary */}
          {detail.random_signals && detail.search_mode === 'random' && (
            <div className="card p-4">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-mg-dim mb-3">Signal Configuration</h4>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MiniStat label="Entry Triggers" value={detail.random_signals.n_entry_triggers.toString()} />
                <MiniStat label="Entry Filters" value={`${detail.random_signals.min_entry_filters}-${detail.random_signals.max_entry_filters}`} />
                <MiniStat label="Exit Triggers" value={`${detail.random_signals.min_exit_triggers}-${detail.random_signals.max_exit_triggers}`} />
                <MiniStat label="Exit Filters" value={`${detail.random_signals.min_exit_filters}-${detail.random_signals.max_exit_filters}`} />
              </div>
            </div>
          )}

          {/* Execution config summary */}
          {detail.execution_config?.base && Object.keys(detail.execution_config.base).length > 0 && (
            <div className="card p-4">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-mg-dim mb-3">
                Execution Config
                {detail.execution_config.sweep_axes?.length > 0 && (
                  <span className="ml-2 text-mg-blue font-normal normal-case tracking-normal">
                    ({detail.execution_config.sweep_axes.length} sweep {detail.execution_config.sweep_axes.length === 1 ? 'axis' : 'axes'})
                  </span>
                )}
              </h4>
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
                {Object.entries(detail.execution_config.base).map(([k, v]) => (
                  <div key={k} className="flex items-baseline gap-2 text-xs">
                    <span className="text-mg-dim truncate">{k}:</span>
                    <span className="font-mono font-medium">{typeof v === 'number' ? v.toLocaleString() : String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div className="bg-mg-elevated rounded-lg p-3 text-center">
      <div className={`font-mono text-lg font-bold ${accent ? 'text-mg-blue' : ''}`}>{value}</div>
      <div className="text-[10px] text-mg-dim uppercase tracking-wider">{label}</div>
    </div>
  )
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-mg-elevated rounded-md px-3 py-2">
      <div className="font-mono text-sm font-bold">{value}</div>
      <div className="text-[10px] text-mg-dim">{label}</div>
    </div>
  )
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
  } catch {
    return iso
  }
}
