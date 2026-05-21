import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const MAX_CHARS = 2000

export default function TextTab({ status, addToast }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const textareaRef = useRef(null)

  const handlePaste = async () => {
    try {
      const clipboard = await navigator.clipboard.readText()
      setText((prev) => prev + clipboard)
      textareaRef.current?.focus()
    } catch {
      addToast('Clipboard access denied — use Ctrl+V instead', 'error')
    }
  }

  const handleSend = async () => {
    if (!text.trim()) { addToast('Nothing to send', 'error'); return }
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    setSending(true)
    try {
      await api.sendText(text.trim())
      addToast('Text sent to glasses', 'success')
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSend()
  }

  const lineCount = text ? text.split('\n').length : 0
  const charCount = text.length

  return (
    <div className="tab-panel">
      <div className="tab-title">Send Text</div>

      <div className="card">
        <div className="card-label">Message</div>
        <textarea
          ref={textareaRef}
          className="textarea"
          placeholder="Type or paste text to display on the glasses…"
          value={text}
          onChange={(e) => setText(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={handleKeyDown}
          spellCheck={false}
        />
        <div className="text-meta">
          <span>{lineCount} line{lineCount !== 1 ? 's' : ''} · {charCount} / {MAX_CHARS} chars</span>
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>⌘↵ to send</span>
        </div>

        <div className="btn-row">
          <button className="btn btn-ghost btn-sm" onClick={handlePaste}>
            <IconClipboard /> Paste
          </button>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setText('')}
            disabled={!text}
          >
            Clear
          </button>
          <button
            className="btn btn-primary"
            onClick={handleSend}
            disabled={sending || !status.connected || !text.trim()}
            title={!status.connected ? 'Connect to glasses first' : ''}
          >
            {sending ? 'Sending…' : 'Send to Glasses'}
          </button>
        </div>
      </div>

      {!status.connected && (
        <div style={{ color: 'var(--muted)', fontSize: 12 }}>
          Connect to glasses on the Home tab before sending.
        </div>
      )}

      <div className="card" style={{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.7 }}>
        <div className="card-label">Display notes</div>
        Text longer than one screen (5 lines × 40 chars) will be split into pages.
        Each page is shown for ~5 seconds before advancing automatically.
      </div>
    </div>
  )
}

function IconClipboard() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
    </svg>
  )
}
