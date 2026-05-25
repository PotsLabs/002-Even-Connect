import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import { api } from './api'
import ComposeTab from './components/ComposeTab'
import Home from './components/Home'
import ImageTab from './components/ImageTab'
import TextTab from './components/TextTab'

const TABS = [
  { id: 'home',    label: 'Home',    icon: <IconHome /> },
  { id: 'image',   label: 'Image',   icon: <IconImage /> },
  { id: 'compose', label: 'Compose', icon: <IconCompose /> },
  { id: 'text',    label: 'Text',    icon: <IconText /> },
]

export default function App() {
  const [tab, setTab] = useState('home')
  const [status, setStatus] = useState({ connected: false, left: false, right: false })
  const [toasts, setToasts] = useState([])
  const [logs, setLogs] = useState([])
  const toastIdRef = useRef(0)

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

  const sharedProps = { status, addToast, addLog }

  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>EvenConnect</h1>
          <p>G1 Glasses Control</p>
        </div>
        <nav className="sidebar-nav">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`nav-btn ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              {t.icon}
              {t.label}
              {t.id === 'home' && (
                <span className={`status-dot-sidebar ${status.connected ? 'on' : ''}`} />
              )}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main */}
      <main className="main">
        {tab === 'home'    && <Home       {...sharedProps} onStatusChange={setStatus} logs={logs} clearLogs={clearLogs} />}
        {tab === 'image'   && <ImageTab   {...sharedProps} />}
        {tab === 'compose' && <ComposeTab {...sharedProps} />}
        {tab === 'text'    && <TextTab    {...sharedProps} />}
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

function IconImage() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}

function IconCompose() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="8" y1="12" x2="16" y2="12" />
      <line x1="8" y1="8" x2="13" y2="8" />
      <line x1="8" y1="16" x2="14" y2="16" />
    </svg>
  )
}

function IconText() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="17" y1="10" x2="3" y2="10" />
      <line x1="21" y1="6" x2="3" y2="6" />
      <line x1="21" y1="14" x2="3" y2="14" />
      <line x1="17" y1="18" x2="3" y2="18" />
    </svg>
  )
}
