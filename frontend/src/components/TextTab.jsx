import { useRef, useState } from 'react'
import { api } from '../api'

const MAX_CHARS = 2000
const STORAGE_KEY = 'evenconnect_notes'

function loadNotes() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] }
}

function persistNotes(notes) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(notes))
}

export default function TextTab({ status, addToast }) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [notes, setNotes] = useState(loadNotes)
  const [saveHeading, setSaveHeading] = useState('')
  const [showSaveForm, setShowSaveForm] = useState(false)
  const textareaRef = useRef(null)
  const headingRef = useRef(null)

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

  const handleSaveNote = () => {
    if (!saveHeading.trim()) { headingRef.current?.focus(); return }
    const note = { id: Date.now(), heading: saveHeading.trim(), text: text.trim() }
    const updated = [note, ...notes]
    setNotes(updated)
    persistNotes(updated)
    setSaveHeading('')
    setShowSaveForm(false)
    addToast('Note saved', 'success')
  }

  const handleLoadNote = (note) => {
    setText(note.text.slice(0, MAX_CHARS))
    addToast(`Loaded "${note.heading}"`, 'info')
    textareaRef.current?.focus()
  }

  const handleDeleteNote = (id) => {
    const updated = notes.filter((n) => n.id !== id)
    setNotes(updated)
    persistNotes(updated)
  }

  const toggleSaveForm = () => {
    setShowSaveForm((v) => !v)
    if (!showSaveForm) setTimeout(() => headingRef.current?.focus(), 0)
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
            className="btn btn-ghost btn-sm"
            onClick={toggleSaveForm}
            disabled={!text.trim()}
            title="Save this text as a named note"
          >
            <IconBookmark /> Save
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

        {showSaveForm && (
          <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
            <input
              ref={headingRef}
              className="note-heading-input"
              placeholder="Note heading…"
              value={saveHeading}
              onChange={(e) => setSaveHeading(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveNote()
                if (e.key === 'Escape') setShowSaveForm(false)
              }}
              maxLength={80}
            />
            <button className="btn btn-primary btn-sm" onClick={handleSaveNote}>
              Save
            </button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowSaveForm(false)}>
              Cancel
            </button>
          </div>
        )}
      </div>

      {!status.connected && (
        <div style={{ color: 'var(--muted)', fontSize: 12 }}>
          Connect to glasses on the Home tab before sending.
        </div>
      )}

      {notes.length > 0 && (
        <div className="card">
          <div className="card-label">Saved Notes</div>
          <div className="notes-list">
            {notes.map((note) => (
              <div key={note.id} className="note-item">
                <div className="note-item-body" onClick={() => handleLoadNote(note)}>
                  <span className="note-heading">{note.heading}</span>
                  <span className="note-preview">{note.text.slice(0, 80)}{note.text.length > 80 ? '…' : ''}</span>
                </div>
                <button
                  className="note-delete-btn"
                  onClick={() => handleDeleteNote(note.id)}
                  title="Delete note"
                >
                  <IconTrash />
                </button>
              </div>
            ))}
          </div>
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

function IconBookmark() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  )
}
