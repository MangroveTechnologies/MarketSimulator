import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import ConfigureView from './views/ConfigureView'
import MonitorView from './views/MonitorView'
import ExploreView from './views/ExploreView'
import ViewTab from './views/ViewTab'
import type { ResultRow } from './types'

export interface SelectedRun {
  experimentId: string
  runIndex: number
  row: ResultRow
}

function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    const saved = localStorage.getItem('mg-theme')
    return (saved === 'light' ? 'light' : 'dark')
  })
  const [selectedRun, setSelectedRun] = useState<SelectedRun | null>(null)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('mg-theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const hasRun = selectedRun !== null

  return (
    <BrowserRouter>
      <div className="min-h-screen bg-mg-bg text-mg-text">
        {/* Navigation */}
        <nav className="border-b border-mg-border bg-mg-surface sticky top-0 z-50">
          <div className="mx-auto px-8 sm:px-12 lg:px-16 flex items-center justify-between h-14">
            <div className="flex items-center gap-8">
              <NavLink to="/explore" className="flex items-center gap-3 shrink-0">
                <img src="/mangrove-mark.svg" alt="Mangrove" className="h-7 w-auto" />
                <span className="subhead text-sm text-mg-text tracking-[0.075em]">Mangrove</span>
              </NavLink>
              <div className="flex gap-2">
                {[
                  { to: '/configure', label: 'Configure' },
                  { to: '/monitor', label: 'Monitor' },
                  { to: '/explore', label: 'Explore' },
                ].map(tab => (
                  <NavLink
                    key={tab.to}
                    to={tab.to}
                    className={({ isActive }) =>
                      `px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                        isActive
                          ? 'bg-mg-elevated text-mg-blue'
                          : 'text-mg-dim hover:text-mg-text hover:bg-mg-hover'
                      }`
                    }
                  >
                    {tab.label}
                  </NavLink>
                ))}
                {/* View tab -- greyed out until a run is selected */}
                <NavLink
                  to="/view"
                  onClick={e => { if (!hasRun) e.preventDefault() }}
                  className={({ isActive }) =>
                    hasRun
                      ? `px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                          isActive
                            ? 'bg-mg-elevated text-mg-blue'
                            : 'text-mg-dim hover:text-mg-text hover:bg-mg-hover'
                        }`
                      : 'px-4 py-2 text-sm font-medium rounded-md text-mg-muted opacity-40 cursor-default'
                  }
                >
                  View
                </NavLink>
              </div>
            </div>
            <button
              onClick={toggleTheme}
              className="px-3 py-1.5 text-xs rounded-md border border-mg-border text-mg-dim hover:text-mg-text hover:border-mg-blue transition-colors"
            >
              {theme === 'dark' ? 'Light' : 'Dark'}
            </button>
          </div>
        </nav>

        {/* Content */}
        <main className="mx-auto px-8 sm:px-12 lg:px-16 py-8">
          <Routes>
            <Route path="/" element={<Navigate to="/explore" replace />} />
            <Route path="/configure" element={<ConfigureView />} />
            <Route path="/monitor" element={<MonitorView />} />
            <Route path="/explore" element={<ExploreView onSelectRun={setSelectedRun} />} />
            <Route path="/view" element={<ViewTab selectedRun={selectedRun} />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
