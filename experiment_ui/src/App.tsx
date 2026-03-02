import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom'
import { useState } from 'react'
import ConfigureView from './views/ConfigureView'
import MonitorView from './views/MonitorView'
import ExploreView from './views/ExploreView'

function App() {
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    document.documentElement.setAttribute('data-theme', next)
  }

  return (
    <BrowserRouter>
      <div className="min-h-screen">
        {/* Navigation */}
        <nav className="border-b border-mg-border bg-mg-surface sticky top-0 z-50">
          <div className="max-w-[1400px] mx-auto px-6 flex items-center justify-between h-14">
            <div className="flex items-center gap-8">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-mg-blue flex items-center justify-center text-xs font-bold text-mg-black">M</div>
                <span className="font-semibold text-sm tracking-wide">MANGROVE</span>
              </div>
              <div className="flex gap-1">
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
        <main className="max-w-[1400px] mx-auto px-6 py-6">
          <Routes>
            <Route path="/" element={<Navigate to="/configure" replace />} />
            <Route path="/configure" element={<ConfigureView />} />
            <Route path="/monitor" element={<MonitorView />} />
            <Route path="/explore" element={<ExploreView />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
