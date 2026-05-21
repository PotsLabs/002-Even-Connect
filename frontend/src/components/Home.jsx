import { useRef, useState } from 'react'
import { api } from '../api'
import Terminal from './Terminal'

export default function Home({ status, onStatusChange, addToast }) {
  const [logs, setLogs] = useState([])
  const [scanning, setScanning] = useState(false)
  const [busy, setBusy] = useState(false)
  const abortRef = useRef(null)

  const handleConnect = async () => {
    // Cancel any in-progress stream
    abortRef.current?.abort()
    const ctrl = new AbortController()
    abortRef.current = ctrl

    setLogs([])
    setScanning(true)
    setBusy(true)

    try {
      const res = await fetch('/api/connect-stream', {
        method: 'POST',
        signal: ctrl.signal,
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() // keep partial line

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const payload = line.slice(6)

          if (payload.startsWith('__DONE__')) {
            const s = JSON.parse(payload.slice(8))
            onStatusChange(s)
            addToast(
              `Connected — L: ${s.leftName || 'n/a'}  R: ${s.rightName || 'n/a'}`,
              'success',
            )
            reader.cancel()
            return
          }

          if (payload.startsWith('__FAIL__')) {
            addToast(payload.slice(8) || 'No glasses found', 'error')
            reader.cancel()
            return
          }

          if (payload.trim()) {
            setLogs((prev) => [...prev, payload])
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') addToast(err.message, 'error')
    } finally {
      setScanning(false)
      setBusy(false)
    }
  }

  const handleDisconnect = async () => {
    abortRef.current?.abort()
    setBusy(true)
    try {
      await api.disconnect()
      onStatusChange({ connected: false, left: false, right: false })
      addToast('Disconnected', 'info')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setBusy(false)
    }
  }

  const dotClass = scanning ? 'pulse' : status.connected ? 'on' : 'off'
  const statusText = scanning
    ? 'Scanning for glasses…'
    : status.connected
    ? 'Connected'
    : 'Not connected'

  return (
    <div className="tab-panel">
      <div className="tab-title">Glasses Connection</div>

      <div className="card">
        <div className="card-label">Status</div>
        <div className="status-row">
          <span className={`status-dot ${dotClass}`} />
          <span className="status-label">{statusText}</span>
        </div>

        {status.connected && (
          <div className="glass-row">
            <div className="glass-chip">
              <div className="glass-chip-title">Left</div>
              <div className="glass-chip-name">
                {status.left
                  ? status.leftName || 'Connected'
                  : <span style={{ color: 'var(--muted)' }}>Not found</span>}
              </div>
            </div>
            <div className="glass-chip">
              <div className="glass-chip-title">Right</div>
              <div className="glass-chip-name">
                {status.right
                  ? status.rightName || 'Connected'
                  : <span style={{ color: 'var(--muted)' }}>Not found</span>}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="btn-row">
        {!status.connected ? (
          <button
            className="btn btn-primary"
            onClick={handleConnect}
            disabled={busy}
          >
            <IconBluetooth />
            {scanning ? 'Scanning…' : 'Connect to Glasses'}
          </button>
        ) : (
          <button
            className="btn btn-danger"
            onClick={handleDisconnect}
            disabled={busy}
          >
            Disconnect
          </button>
        )}
        {logs.length > 0 && !scanning && (
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setLogs([])}
          >
            Clear
          </button>
        )}
      </div>

      <Terminal lines={logs} active={scanning} />
    </div>
  )
}

function IconBluetooth() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6.5 6.5 17.5 17.5 12 23 12 1 17.5 6.5 6.5 17.5" />
    </svg>
  )
}
