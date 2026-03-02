import { useState, useEffect } from 'react'
import { listExperiments, getExperiment } from '../api/client'
import type { ExperimentSummary } from '../types'

const STATUS_COLORS: Record<string, string> = {
  draft: 'bg-mg-muted',
  validated: 'bg-mg-blue',
  running: 'bg-green-500',
  paused: 'bg-mg-orange',
  completed: 'bg-mg-blue',
  failed: 'bg-mg-red',
}

export default function MonitorView() {
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [detail, setDetail] = useState<any>(null)

  useEffect(() => {
    const load = async () => {
      const exps = await listExperiments()
      setExperiments(exps)
    }
    load()
    const interval = setInterval(load, 10000) // refresh every 10s
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

  return (
    <div>
      <h1 className="text-xl font-bold mb-4">Experiment Monitor</h1>

      {/* Experiment list */}
      <div className="border border-mg-border rounded-lg bg-mg-surface overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead>
            <tr>
              {['Name', 'Status', 'Total Runs', 'Mode', 'Created'].map(h => (
                <th key={h} className="text-left px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-mg-dim border-b border-mg-border">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {experiments.map(e => (
              <tr
                key={e.experiment_id}
                onClick={() => setSelectedId(e.experiment_id)}
                className={`cursor-pointer border-b border-mg-border/50 hover:bg-mg-hover transition-colors
                  ${selectedId === e.experiment_id ? 'bg-mg-blue/5' : ''}`}
              >
                <td className="px-3 py-2 font-medium">{e.name}</td>
                <td className="px-3 py-2">
                  <span className={`inline-flex items-center gap-1.5 text-xs font-semibold`}>
                    <span className={`w-2 h-2 rounded-full ${STATUS_COLORS[e.status] || 'bg-gray-500'}`} />
                    {e.status}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{e.total_runs?.toLocaleString() ?? '-'}</td>
                <td className="px-3 py-2 text-xs text-mg-dim">{e.search_mode}</td>
                <td className="px-3 py-2 text-xs text-mg-dim">{new Date(e.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Detail */}
      {detail && (
        <div className="border border-mg-border rounded-lg bg-mg-surface p-4">
          <h3 className="font-semibold mb-3">{detail.name}</h3>
          <div className="grid grid-cols-4 gap-4 mb-4">
            <Stat label="Status" value={detail.status} />
            <Stat label="Total Runs" value={detail.total_runs?.toLocaleString() ?? '-'} />
            <Stat label="Completed" value={detail.completed_runs?.toLocaleString() ?? '-'} />
            <Stat label="Search Mode" value={detail.search_mode} />
          </div>
          {detail.status === 'running' && (
            <div className="bg-mg-elevated rounded-lg p-3">
              <div className="flex justify-between text-xs text-mg-dim mb-1">
                <span>Progress</span>
                <span>{detail.completed_runs ?? 0} / {detail.total_runs ?? 0}</span>
              </div>
              <div className="h-2 bg-mg-border rounded-full overflow-hidden">
                <div
                  className="h-full bg-mg-blue rounded-full transition-all duration-500"
                  style={{ width: `${detail.total_runs ? ((detail.completed_runs || 0) / detail.total_runs * 100) : 0}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-mg-elevated rounded-lg p-3 text-center">
      <div className="font-mono text-lg font-bold">{value}</div>
      <div className="text-[10px] text-mg-dim uppercase tracking-wider">{label}</div>
    </div>
  )
}
