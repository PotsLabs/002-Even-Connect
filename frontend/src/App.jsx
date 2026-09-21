import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import { api, apiUrl } from './api'
import Home from './components/Home'
import TextTab from './components/TextTab'
import ComposeTab from './components/ComposeTab'
import Models3D from './components/Models3D'
import ObsidianTab from './components/ObsidianTab'

const TABS = [
  { id: 'home',     label: 'Home',     icon: <IconHome /> },
  { id: 'text',     label: 'Text',     icon: <IconText /> },
  { id: 'compose',  label: 'Compose',  icon: <IconCompose /> },
  { id: 'models',   label: '3D',       icon: <Icon3D /> },
  { id: 'obsidian', label: 'Obsidian', icon: <IconObsidian /> },
]

export default function App() {
  const [tab, setTab] = useState('home')
  const [status, setStatus] = useState({ connected: false, left: false, right: false })
  const [toasts, setToasts] = useState([])
  const [logs, setLogs] = useState([])
  const toastIdRef = useRef(0)
  // Lazy-mount: track which tabs have been visited so their state survives tab switches
  const [visited, setVisited] = useState(() => new Set(['home']))

  // Poll connection status every 4 s
  useEffect(() => {
    const poll = async () => {
      try { setStatus(await api.status()) } catch { /* backend not up yet */ }
    }
    poll()
    const id = setInterval(poll, 4000)
    return () => clearInterval(id)
  }, [])

  const addToast = useCallback((message, type = 'info') => {
    const id = ++toastIdRef.current
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 3500)
  }, [])

  const addLog = useCallback((line) => setLogs((prev) => [...prev, line]), [])
  const clearLogs = useCallback(() => setLogs([]), [])

  // Stream touchpad / wear events from the glasses into the activity log
  useEffect(() => {
    if (!status.connected) return
    const es = new EventSource(apiUrl('/events/stream'))
    es.onmessage = (e) => {
      if (e.data && e.data.trim()) addLog(e.data)
    }
    es.onerror = () => {}  // reconnects automatically; suppress noise
    return () => es.close()
  }, [status.connected, addLog])

  const sharedProps = { status, addToast, addLog }

  return (
    <div className="layout">
      {/* Top tab bar */}
      <nav className="topbar">
        <span className="topbar-brand">KiroshiOS</span>
        <div className="topbar-tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`nav-btn ${tab === t.id ? 'active' : ''}`}
              onClick={() => { setTab(t.id); setVisited(v => new Set([...v, t.id])) }}
            >
              {t.icon}
              {t.label}
              {t.id === 'home' && (
                <span className={`status-dot-sidebar ${status.connected ? 'on' : ''}`} />
              )}
            </button>
          ))}
        </div>
      </nav>

      {/* Main */}
      <main className="main">
        {tab === 'home' && <Home {...sharedProps} onStatusChange={setStatus} logs={logs} clearLogs={clearLogs} />}
        {tab === 'text' && <TextTab {...sharedProps} />}
        {tab === 'compose' && <ComposeTab {...sharedProps} />}
        {tab === 'models' && <Models3D {...sharedProps} />}
        {tab === 'obsidian' && <ObsidianTab {...sharedProps} />}
      </main>

      {/* Toast notifications */}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div key={t.id} className={`toast ${t.type}`}>{t.message}</div>
        ))}
      </div>
    </div>
  )
}

function IconHome() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  )
}

function IconText() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h10" />
    </svg>
  )
}

function IconCompose() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 6 20 3 3 20 3 23 6 23 23 6" />
    </svg>
  )
}

function Icon3D() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  )
}

function IconObsidian() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L4 7v10l8 5 8-5V7z" />
      <path d="M12 2v20" />
      <path d="M4 7l8 5 8-5" />
    </svg>
  )
}
