import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import { api } from './api'
import Home from './components/Home'
import ImageTab from './components/ImageTab'
import ObsidianTab from './components/ObsidianTab'
import SendTab from './components/SendTab'

const TABS = [
  { id: 'home',     label: 'Home',     icon: <IconHome /> },
  { id: 'image',    label: 'Image',    icon: <IconImage /> },
  { id: 'send',     label: 'Send',     icon: <IconSend /> },
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
    const es = new EventSource('/api/events/stream')
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

        {/* Image tab: lazy-mount then keep alive so queue state survives tab switches */}
        {visited.has('image') && (
          <div style={{ display: tab === 'image' ? 'contents' : 'none' }}>
            <ImageTab {...sharedProps} />
          </div>
        )}

        {visited.has('send') && (
          <div style={{ display: tab === 'send' ? 'contents' : 'none' }}>
            <SendTab {...sharedProps} />
          </div>
        )}
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

function IconImage() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}

function IconSend() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
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
