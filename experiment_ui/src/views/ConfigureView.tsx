import { useState, useEffect, useCallback } from 'react'
import {
  getDatasets, getSignals, getExecDefaults,
  createExperiment, validateExperiment, launchExperiment,
  listTemplates, getTemplate, saveTemplate,
} from '../api/client'
import type { Dataset, Signal } from '../types'
import { ChevronDownIcon } from '@heroicons/react/20/solid'

// ── Collapsible section ──────────────────────────────────────────

function Section({ title, badge, defaultOpen = true, children }: {
  title: string; badge?: string; defaultOpen?: boolean; children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="card overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-mg-hover transition-colors"
      >
        <span className="text-[11px] font-semibold uppercase tracking-wider text-mg-dim">{title}</span>
        <div className="flex items-center gap-2">
          {badge && <span className="badge-trigger">{badge}</span>}
          <ChevronDownIcon className={`w-4 h-4 text-mg-dim transition-transform ${open ? '' : '-rotate-90'}`} />
        </div>
      </button>
      {open && <div className="px-4 pb-4 border-t border-subtle">{children}</div>}
    </div>
  )
}

// ── Main view ────────────────────────────────────────────────────

export default function ConfigureView() {
  // Data sources
  const [datasets, setDatasets] = useState<Dataset[]>([])
  const [signals, setSignals] = useState<Signal[]>([])
  const [execDefaults, setExecDefaults] = useState<Record<string, any>>({})
  const [templates, setTemplates] = useState<{ name: string; description: string; search_mode: string; datasets_count: number }[]>([])

  // Form state
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [seed, setSeed] = useState(42)
  const [searchMode, setSearchMode] = useState<'random' | 'grid'>('random')
  const [selectedDatasets, setSelectedDatasets] = useState<Set<string>>(new Set())
  const [datasetSearch, setDatasetSearch] = useState('')

  // Random mode
  const [nRandom, setNRandom] = useState(10000)
  const [nEntryTriggers, setNEntryTriggers] = useState(1)
  const [minEntryFilters, setMinEntryFilters] = useState(1)
  const [maxEntryFilters, setMaxEntryFilters] = useState(3)
  const [minExitTriggers, setMinExitTriggers] = useState(0)
  const [maxExitTriggers, setMaxExitTriggers] = useState(1)
  const [minExitFilters, setMinExitFilters] = useState(0)
  const [maxExitFilters, setMaxExitFilters] = useState(3)
  const [nParamDraws, setNParamDraws] = useState(1)

  // Exec config overrides
  const [execOverrides, setExecOverrides] = useState<Record<string, string>>({})

  // Lifecycle
  const [createdId, setCreatedId] = useState('')
  const [validationResult, setValidationResult] = useState<any>(null)
  const [launching, setLaunching] = useState(false)
  const [error, setError] = useState('')

  // Load data on mount
  useEffect(() => {
    getDatasets().then(setDatasets)
    getSignals().then(setSignals)
    getExecDefaults().then(setExecDefaults)
    listTemplates().then(setTemplates)
  }, [])

  // Dataset filtering
  const filteredDatasets = datasets.filter(d => {
    if (!datasetSearch) return true
    const q = datasetSearch.toLowerCase()
    return d.asset.toLowerCase().includes(q) || d.timeframe.toLowerCase().includes(q)
  })

  const toggleDataset = (file: string) => {
    setSelectedDatasets(prev => {
      const next = new Set(prev)
      if (next.has(file)) next.delete(file)
      else next.add(file)
      return next
    })
  }

  const selectAllDatasets = () => {
    if (selectedDatasets.size === filteredDatasets.length) {
      setSelectedDatasets(new Set())
    } else {
      setSelectedDatasets(new Set(filteredDatasets.map(d => d.file)))
    }
  }

  // Load template
  const loadTemplate = async (tplName: string) => {
    try {
      const tpl = await getTemplate(tplName)
      setName(tpl.name || tplName)
      setDescription(tpl.description || '')
      setSeed(tpl.seed || 42)
      setSearchMode(tpl.search_mode || 'random')
      if (tpl.datasets) {
        setSelectedDatasets(new Set(tpl.datasets.map((d: any) => d.file)))
      }
      if (tpl.n_random) setNRandom(tpl.n_random)
      if (tpl.random_signals) {
        const rs = tpl.random_signals
        setNEntryTriggers(rs.n_entry_triggers ?? 1)
        setMinEntryFilters(rs.min_entry_filters ?? 1)
        setMaxEntryFilters(rs.max_entry_filters ?? 3)
        setMinExitTriggers(rs.min_exit_triggers ?? 0)
        setMaxExitTriggers(rs.max_exit_triggers ?? 1)
        setMinExitFilters(rs.min_exit_filters ?? 0)
        setMaxExitFilters(rs.max_exit_filters ?? 3)
        setNParamDraws(rs.n_param_draws ?? 1)
      }
      if (tpl.execution_config?.base) {
        const overrides: Record<string, string> = {}
        for (const [k, v] of Object.entries(tpl.execution_config.base)) {
          overrides[k] = String(v)
        }
        setExecOverrides(overrides)
      }
    } catch (e) {
      setError('Failed to load template')
    }
  }

  // Build config object
  const buildConfig = useCallback(() => {
    const selectedDs = datasets.filter(d => selectedDatasets.has(d.file)).map(d => ({
      asset: d.asset,
      timeframe: d.timeframe,
      file: d.file,
      hash: d.hash,
      rows: d.rows,
      start_date: d.start_date,
      end_date: d.end_date,
    }))

    const execBase: Record<string, any> = { ...execDefaults }
    for (const [k, v] of Object.entries(execOverrides)) {
      if (v !== '') {
        const num = Number(v)
        execBase[k] = isNaN(num) ? v : num
      }
    }

    return {
      name: name || `experiment_${Date.now()}`,
      description,
      seed,
      search_mode: searchMode,
      n_random: searchMode === 'random' ? nRandom : null,
      random_signals: searchMode === 'random' ? {
        n_entry_triggers: nEntryTriggers,
        min_entry_filters: minEntryFilters,
        max_entry_filters: maxEntryFilters,
        min_exit_triggers: minExitTriggers,
        max_exit_triggers: maxExitTriggers,
        min_exit_filters: minExitFilters,
        max_exit_filters: maxExitFilters,
        n_param_draws: nParamDraws,
      } : undefined,
      datasets: selectedDs,
      execution_config: {
        base: execBase,
        sweep_axes: [],
      },
    }
  }, [name, description, seed, searchMode, nRandom, datasets, selectedDatasets, execDefaults, execOverrides,
    nEntryTriggers, minEntryFilters, maxEntryFilters, minExitTriggers, maxExitTriggers, minExitFilters, maxExitFilters, nParamDraws])

  // Actions
  const handleCreate = async () => {
    setError('')
    setValidationResult(null)
    try {
      const config = buildConfig()
      const result = await createExperiment(config)
      setCreatedId(result.experiment_id)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to create experiment')
    }
  }

  const handleValidate = async () => {
    if (!createdId) return
    setError('')
    try {
      const result = await validateExperiment(createdId)
      setValidationResult(result)
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      if (typeof detail === 'object') {
        setValidationResult({ valid: false, ...detail })
      } else {
        setError(detail || 'Validation failed')
      }
    }
  }

  const handleLaunch = async () => {
    if (!createdId) return
    setLaunching(true)
    setError('')
    try {
      await launchExperiment(createdId)
      window.location.href = '/monitor'
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Launch failed')
    }
    setLaunching(false)
  }

  const handleSaveTemplate = async () => {
    const tplName = name || 'untitled'
    try {
      await saveTemplate(tplName, buildConfig())
      listTemplates().then(setTemplates)
    } catch (e) {
      setError('Failed to save template')
    }
  }

  const triggerCount = signals.filter(s => s.type === 'TRIGGER').length
  const filterCount = signals.filter(s => s.type === 'FILTER').length
  const totalRuns = searchMode === 'random' ? selectedDatasets.size * nRandom : 0

  return (
    <div className="space-y-4 pb-24">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold tracking-wide uppercase text-mg-dim">Configure Experiment</h1>
        {templates.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-mg-muted">Template:</span>
            <select
              onChange={e => { if (e.target.value) loadTemplate(e.target.value) }}
              className="input text-xs"
              defaultValue=""
            >
              <option value="">Load template...</option>
              {templates.map(t => <option key={t.name} value={t.name}>{t.name}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* 1. Experiment Name */}
      <Section title="Experiment Name" defaultOpen={true}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3">
          <div>
            <label className="text-xs text-mg-dim block mb-1">Name</label>
            <input
              type="text" value={name} onChange={e => setName(e.target.value)}
              placeholder="e.g. momentum_sweep_v1"
              className="input w-full text-sm font-mono"
            />
          </div>
          <div>
            <label className="text-xs text-mg-dim block mb-1">Seed</label>
            <input
              type="number" value={seed} onChange={e => setSeed(Number(e.target.value))}
              className="w-full bg-mg-elevated border border-mg-border rounded-md px-3 py-2 text-sm font-mono text-mg-text focus:outline-none focus:border-mg-blue"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="text-xs text-mg-dim block mb-1">Description</label>
            <textarea
              value={description} onChange={e => setDescription(e.target.value)}
              rows={2} placeholder="Optional description..."
              className="input w-full text-sm resize-none"
            />
          </div>
        </div>
      </Section>

      {/* 2. Datasets */}
      <Section title="Datasets" badge={`${selectedDatasets.size} selected`}>
        <div className="mt-3 space-y-2">
          <input
            type="text" value={datasetSearch} onChange={e => setDatasetSearch(e.target.value)}
            placeholder="Search datasets..."
            className="input w-full text-sm"
          />
          <div className="card overflow-hidden max-h-[300px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-mg-surface">
                <tr>
                  <th className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-mg-dim border-b border-mg-border w-10">
                    <input
                      type="checkbox"
                      checked={selectedDatasets.size === filteredDatasets.length && filteredDatasets.length > 0}
                      onChange={selectAllDatasets}
                      className="accent-[#42A7C6]"
                    />
                  </th>
                  {['Asset', 'TF', 'Start', 'End', 'Rows'].map(h => (
                    <th key={h} className="text-left px-3 py-2 text-[10px] font-semibold uppercase tracking-wider text-mg-dim border-b border-mg-border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredDatasets.map(d => (
                  <tr
                    key={d.file}
                    onClick={() => toggleDataset(d.file)}
                    className={`cursor-pointer row-border-subtle hover:bg-mg-hover transition-colors
                      ${selectedDatasets.has(d.file) ? 'border-l-2 border-l-mg-blue' : 'border-l-2 border-l-transparent'}`}
                  >
                    <td className="px-3 py-1.5">
                      <input type="checkbox" checked={selectedDatasets.has(d.file)} readOnly className="accent-[#42A7C6] pointer-events-none" />
                    </td>
                    <td className="px-3 py-1.5 font-semibold">{d.asset}</td>
                    <td className="px-3 py-1.5 font-mono text-xs">{d.timeframe}</td>
                    <td className="px-3 py-1.5 font-mono text-xs text-mg-dim">{d.start_date}</td>
                    <td className="px-3 py-1.5 font-mono text-xs text-mg-dim">{d.end_date}</td>
                    <td className="px-3 py-1.5 font-mono text-xs text-right">{d.rows.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Section>

      {/* 3. Search Mode & Signal Config */}
      <Section title="Search Mode & Signals" badge={searchMode}>
        <div className="mt-3 space-y-4">
          {/* Mode selector */}
          <div className="flex gap-4">
            {(['random', 'grid'] as const).map(mode => (
              <label key={mode} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio" name="searchMode" value={mode}
                  checked={searchMode === mode}
                  onChange={() => setSearchMode(mode)}
                  className="accent-[#42A7C6]"
                />
                <span className="text-sm font-medium capitalize">{mode}</span>
                <span className="text-[10px] text-mg-muted">
                  {mode === 'random' ? '(sample N runs)' : '(enumerate combos)'}
                </span>
              </label>
            ))}
          </div>

          {/* Signal pool summary */}
          <div className="flex gap-4 text-xs">
            <span className="px-2 py-1 rounded bg-blue-10 text-mg-blue font-medium">{triggerCount} triggers</span>
            <span className="px-2 py-1 rounded bg-orange-10 text-mg-orange font-medium">{filterCount} filters</span>
          </div>

          {searchMode === 'random' && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-mg-dim block mb-1">N per dataset</label>
                <input
                  type="number" value={nRandom} onChange={e => setNRandom(Number(e.target.value))}
                  className="input w-40 text-sm font-mono"
                />
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <NumField label="Entry triggers" value={nEntryTriggers} onChange={setNEntryTriggers} />
                <NumField label="Min entry filters" value={minEntryFilters} onChange={setMinEntryFilters} />
                <NumField label="Max entry filters" value={maxEntryFilters} onChange={setMaxEntryFilters} />
                <NumField label="Param draws" value={nParamDraws} onChange={setNParamDraws} />
                <NumField label="Min exit triggers" value={minExitTriggers} onChange={setMinExitTriggers} />
                <NumField label="Max exit triggers" value={maxExitTriggers} onChange={setMaxExitTriggers} />
                <NumField label="Min exit filters" value={minExitFilters} onChange={setMinExitFilters} />
                <NumField label="Max exit filters" value={maxExitFilters} onChange={setMaxExitFilters} />
              </div>
            </div>
          )}

          {searchMode === 'grid' && (
            <div className="text-sm text-mg-dim bg-mg-elevated rounded-lg p-4">
              Grid mode requires selecting specific signals and defining parameter sweeps.
              This is available in the API but not yet in the UI -- use the API directly or switch to random mode.
            </div>
          )}
        </div>
      </Section>

      {/* 4. Execution Config */}
      <Section title="Execution Config" defaultOpen={false}>
        <div className="mt-3">
          {Object.keys(execDefaults).length === 0 ? (
            <div className="text-sm text-mg-dim">Loading defaults...</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {Object.entries(execDefaults).map(([key, defaultVal]) => (
                <div key={key}>
                  <label className="text-[10px] text-mg-dim block mb-0.5 truncate" title={key}>{key}</label>
                  <input
                    type="text"
                    value={execOverrides[key] ?? ''}
                    placeholder={String(defaultVal)}
                    onChange={e => setExecOverrides(prev => ({ ...prev, [key]: e.target.value }))}
                    className="input w-full text-xs font-mono"
                  />
                </div>
              ))}
            </div>
          )}
        </div>
      </Section>

      {/* Stats bar (sticky) */}
      <div className="fixed bottom-0 left-0 right-0 bg-mg-surface border-t border-mg-border z-40">
        <div className="max-w-[1440px] mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <StatChip label="Datasets" value={selectedDatasets.size} />
            <StatChip label="Triggers" value={triggerCount} />
            <StatChip label="Filters" value={filterCount} />
            <StatChip label="Total Runs" value={totalRuns.toLocaleString()} accent />
          </div>

          <div className="flex items-center gap-3">
            {/* Error display */}
            {error && <span className="text-xs text-mg-red max-w-xs truncate">{error}</span>}

            {/* Validation result */}
            {validationResult && (
              <span className={`text-xs font-medium ${validationResult.valid ? 'text-mg-blue' : 'text-mg-red'}`}>
                {validationResult.valid
                  ? `Valid: ${validationResult.total_runs?.toLocaleString()} runs`
                  : `Invalid: ${validationResult.errors?.[0] || 'check config'}`
                }
              </span>
            )}

            <button
              onClick={handleSaveTemplate}
              className="btn-secondary text-xs"
            >
              Save Template
            </button>

            {!createdId ? (
              <button
                onClick={handleCreate}
                disabled={selectedDatasets.size === 0 || !name}
                className="btn-secondary text-xs"
              >
                Create
              </button>
            ) : !validationResult?.valid ? (
              <button
                onClick={handleValidate}
                className="btn-secondary text-xs !border-mg-blue !text-mg-blue hover:bg-blue-10"
              >
                Validate
              </button>
            ) : (
              <button
                onClick={handleLaunch}
                disabled={launching}
                className="btn-primary text-xs"
              >
                {launching ? 'Launching...' : 'Launch Experiment'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────

function NumField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div>
      <label className="text-[10px] text-mg-dim block mb-0.5">{label}</label>
      <input
        type="number" value={value} onChange={e => onChange(Number(e.target.value))}
        className="input w-full text-xs font-mono"
      />
    </div>
  )
}

function StatChip({ label, value, accent }: { label: string; value: string | number; accent?: boolean }) {
  return (
    <div className="text-center">
      <div className={`font-mono text-sm font-bold ${accent ? 'text-mg-blue' : ''}`}>{value}</div>
      <div className="text-[9px] text-mg-muted uppercase tracking-wider">{label}</div>
    </div>
  )
}
