import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

const CFG_KEY = 'evenconnect_obsidian_cfg'

function loadLocalCfg() {
  try { return JSON.parse(localStorage.getItem(CFG_KEY) || '{}') } catch { return {} }
}

export default function ObsidianTab({ status, addToast }) {
  // Config
  const [cfgUrl, setCfgUrl]       = useState(() => loadLocalCfg().url     || 'https://127.0.0.1:27124')
  const [cfgKey, setCfgKey]       = useState(() => loadLocalCfg().api_key || '')
  const [connected, setConnected] = useState(false)
  const [pinging, setPinging]     = useState(false)

  // File browser
  const [files, setFiles]         = useState([])
  const [loadingFiles, setLoadingFiles] = useState(false)
  const [filterText, setFilterText]     = useState('')

  // Search
  const [searchQuery, setSearchQuery]   = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [searching, setSearching]       = useState(false)

  // Editor
  const [openPath, setOpenPath]   = useState(null)
  const [content, setContent]     = useState('')
  const [dirty, setDirty]         = useState(false)
  const [saving, setSaving]       = useState(false)
  const [sending, setSending]     = useState(false)
  const [loading, setLoading]     = useState(false)
  const [newFilePath, setNewFilePath] = useState('')
  const [showNewFile, setShowNewFile] = useState(false)
  const newFileRef = useRef(null)

  // ── Config & connection ─────────────────────────────────────────────────

  const handleSaveConfig = async () => {
    setPinging(true)
    try {
      await api.obsidian.setConfig(cfgUrl, cfgKey)
      const res = await api.obsidian.ping()
      setConnected(res.ok)
      localStorage.setItem(CFG_KEY, JSON.stringify({ url: cfgUrl, api_key: cfgKey }))
      if (res.ok) {
        addToast('Connected to Obsidian', 'success')
        fetchFiles()
      } else {
        addToast('Obsidian responded but returned an error', 'error')
      }
    } catch (e) {
      setConnected(false)
      addToast(e.message, 'error')
    } finally {
      setPinging(false)
    }
  }

  // Push saved config to backend on mount
  useEffect(() => {
    const cfg = loadLocalCfg()
    if (cfg.url || cfg.api_key) {
      api.obsidian.setConfig(cfg.url || 'https://127.0.0.1:27124', cfg.api_key || '')
        .then(() => api.obsidian.ping())
        .then((res) => { if (res.ok) { setConnected(true); fetchFiles() } })
        .catch(() => {})
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── File list ───────────────────────────────────────────────────────────

  const fetchFiles = useCallback(async () => {
    setLoadingFiles(true)
    try {
      const res = await api.obsidian.listFiles()
      setFiles((res.files || []).filter((f) => f.endsWith('.md')))
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setLoadingFiles(false)
    }
  }, [addToast])

  const visibleFiles = searchResults !== null
    ? searchResults.map((r) => r.filename)
    : files.filter((f) => !filterText || f.toLowerCase().includes(filterText.toLowerCase()))

  // ── Editor ──────────────────────────────────────────────────────────────

  const openFile = useCallback(async (path) => {
    if (dirty) {
      const ok = window.confirm(`Discard unsaved changes in "${openPath}"?`)
      if (!ok) return
    }
    setLoading(true)
    setSearchResults(null)
    try {
      const res = await api.obsidian.getFile(path)
      setOpenPath(path)
      setContent(res.content)
      setDirty(false)
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [dirty, openPath, addToast])

  const handleSave = async () => {
    if (!openPath) return
    setSaving(true)
    try {
      await api.obsidian.writeFile(openPath, content)
      setDirty(false)
      addToast('Saved to Obsidian', 'success')
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleSendToGlasses = async () => {
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    if (!content.trim()) { addToast('Nothing to send', 'error'); return }
    setSending(true)
    try {
      await api.sendText(content.trim())
      addToast('Note sent to glasses', 'success')
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSending(false)
    }
  }

  const handleCreateFile = async () => {
    const p = newFilePath.trim().replace(/^\/+/, '')
    if (!p) { newFileRef.current?.focus(); return }
    const full = p.endsWith('.md') ? p : `${p}.md`
    try {
      await api.obsidian.writeFile(full, '')
      addToast(`Created ${full}`, 'success')
      setNewFilePath('')
      setShowNewFile(false)
      await fetchFiles()
      openFile(full)
    } catch (e) {
      addToast(e.message, 'error')
    }
  }

  const handleDeleteOpen = async () => {
    if (!openPath) return
    if (!window.confirm(`Delete "${openPath}" from Obsidian? This cannot be undone.`)) return
    try {
      await api.obsidian.deleteFile(openPath)
      addToast(`Deleted ${openPath}`, 'success')
      setOpenPath(null)
      setContent('')
      setDirty(false)
      await fetchFiles()
    } catch (e) {
      addToast(e.message, 'error')
    }
  }

  // ── Search ──────────────────────────────────────────────────────────────

  const handleSearch = async (e) => {
    e?.preventDefault()
    if (!searchQuery.trim()) { setSearchResults(null); return }
    setSearching(true)
    try {
      const res = await api.obsidian.search(searchQuery.trim())
      setSearchResults(Array.isArray(res) ? res : [])
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSearching(false)
    }
  }

  const clearSearch = () => {
    setSearchQuery('')
    setSearchResults(null)
  }

  // ── Keyboard shortcuts ──────────────────────────────────────────────────

  const handleEditorKey = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') { e.preventDefault(); handleSave() }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); handleSendToGlasses() }
  }

  // ── Render ──────────────────────────────────────────────────────────────

  const noteName = openPath ? openPath.split('/').pop().replace(/\.md$/, '') : ''

  return (
    <div className="tab-panel">
      <div className="tab-title">Obsidian</div>

      {/* Config card */}
      <div className="card">
        <div className="card-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          Local REST API
          <span style={{
            display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
            background: connected ? 'var(--green)' : 'var(--border)', flexShrink: 0,
          }} />
          {connected && <span style={{ color: 'var(--green)', fontWeight: 500 }}>Connected</span>}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div style={{ flex: '1 1 200px' }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>URL</div>
            <input
              className="note-heading-input"
              value={cfgUrl}
              onChange={(e) => setCfgUrl(e.target.value)}
              placeholder="https://127.0.0.1:27124"
              style={{ width: '100%' }}
            />
          </div>
          <div style={{ flex: '2 1 260px' }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>API Key</div>
            <input
              className="note-heading-input"
              type="password"
              value={cfgKey}
              onChange={(e) => setCfgKey(e.target.value)}
              placeholder="Paste from Obsidian → Local REST API settings"
              style={{ width: '100%' }}
            />
          </div>
          <button className="btn btn-primary btn-sm" onClick={handleSaveConfig} disabled={pinging}>
            {pinging ? 'Connecting…' : 'Connect'}
          </button>
          {connected && (
            <button className="btn btn-ghost btn-sm" onClick={fetchFiles} disabled={loadingFiles}>
              {loadingFiles ? '…' : 'Refresh'}
            </button>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
          Requires the <strong>Local REST API</strong> community plugin in Obsidian (Settings → Community plugins).
        </div>
      </div>

      {connected && (
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', marginTop: 4 }}>

          {/* ── Left column: file browser + search ── */}
          <div style={{ width: 240, flexShrink: 0 }}>

            {/* Search */}
            <form onSubmit={handleSearch} style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
              <input
                className="note-heading-input"
                placeholder="Search vault…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{ flex: 1, minWidth: 0 }}
              />
              <button className="btn btn-ghost btn-sm" type="submit" disabled={searching}>
                {searching ? '…' : <IconSearch />}
              </button>
              {searchResults !== null && (
                <button className="btn btn-ghost btn-sm" type="button" onClick={clearSearch} title="Clear search">
                  ×
                </button>
              )}
            </form>

            {/* Filter (when not searching) */}
            {searchResults === null && (
              <input
                className="note-heading-input"
                placeholder="Filter files…"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                style={{ width: '100%', marginBottom: 8 }}
              />
            )}

            {searchResults !== null && (
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>
                {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} for "{searchQuery}"
              </div>
            )}

            {/* File list */}
            <div style={{
              maxHeight: 420, overflowY: 'auto',
              background: 'var(--surface)', borderRadius: 6,
              border: '1px solid var(--border)',
            }}>
              {loadingFiles ? (
                <div style={{ padding: 12, color: 'var(--muted)', fontSize: 12 }}>Loading…</div>
              ) : visibleFiles.length === 0 ? (
                <div style={{ padding: 12, color: 'var(--muted)', fontSize: 12 }}>
                  {filterText || searchQuery ? 'No matches' : 'No notes found'}
                </div>
              ) : visibleFiles.map((f) => (
                <button
                  key={f}
                  onClick={() => openFile(f)}
                  style={{
                    display: 'block', width: '100%', textAlign: 'left',
                    padding: '7px 10px', border: 'none', cursor: 'pointer',
                    background: openPath === f ? 'var(--accent-dim)' : 'transparent',
                    color: openPath === f ? 'var(--accent)' : 'var(--text)',
                    fontSize: 12, fontFamily: 'var(--font-body)',
                    borderBottom: '1px solid var(--border)',
                    lineHeight: 1.4,
                  }}
                >
                  <div style={{ fontWeight: openPath === f ? 600 : 400, wordBreak: 'break-all' }}>
                    {f.split('/').pop().replace(/\.md$/, '')}
                  </div>
                  {f.includes('/') && (
                    <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 1 }}>
                      {f.substring(0, f.lastIndexOf('/'))}
                    </div>
                  )}
                  {searchResults !== null && (() => {
                    const sr = searchResults.find((r) => r.filename === f)
                    const ctx = sr?.matches?.[0]?.context
                    return ctx ? (
                      <div style={{ fontSize: 10, color: 'var(--muted)', marginTop: 3, fontStyle: 'italic' }}>
                        {ctx.slice(0, 80)}{ctx.length > 80 ? '…' : ''}
                      </div>
                    ) : null
                  })()}
                </button>
              ))}
            </div>

            {/* New file */}
            <div style={{ marginTop: 8 }}>
              {showNewFile ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <input
                    ref={newFileRef}
                    className="note-heading-input"
                    placeholder="path/to/note.md"
                    value={newFilePath}
                    onChange={(e) => setNewFilePath(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleCreateFile()
                      if (e.key === 'Escape') setShowNewFile(false)
                    }}
                    style={{ width: '100%' }}
                  />
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button className="btn btn-primary btn-sm" onClick={handleCreateFile}>Create</button>
                    <button className="btn btn-ghost btn-sm" onClick={() => setShowNewFile(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <button
                  className="btn btn-ghost btn-sm"
                  style={{ width: '100%' }}
                  onClick={() => { setShowNewFile(true); setTimeout(() => newFileRef.current?.focus(), 0) }}
                >
                  + New note
                </button>
              )}
            </div>
          </div>

          {/* ── Right column: editor ── */}
          <div style={{ flex: 1, minWidth: 0 }}>
            {openPath ? (
              <div className="card" style={{ margin: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: 'var(--font-heading)', fontSize: 16, fontWeight: 600, flex: 1 }}>
                    {noteName}
                    {dirty && <span style={{ color: 'var(--yellow)', marginLeft: 6, fontSize: 13 }}>●</span>}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--muted)', wordBreak: 'break-all' }}>{openPath}</span>
                </div>

                {loading ? (
                  <div style={{ color: 'var(--muted)', padding: '24px 0', textAlign: 'center' }}>Loading…</div>
                ) : (
                  <textarea
                    className="textarea"
                    value={content}
                    onChange={(e) => { setContent(e.target.value); setDirty(true) }}
                    onKeyDown={handleEditorKey}
                    style={{ minHeight: 360, fontFamily: 'var(--font-mono)', fontSize: 12 }}
                    spellCheck={false}
                  />
                )}

                <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleSave}
                    disabled={saving || !dirty}
                    title="⌘S"
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => openFile(openPath)}
                    disabled={loading}
                    title="Discard changes"
                  >
                    Revert
                  </button>
                  <button
                    className="btn btn-primary"
                    onClick={handleSendToGlasses}
                    disabled={sending || !status.connected || !content.trim()}
                    title={!status.connected ? 'Connect glasses first' : '⌘↵'}
                  >
                    {sending ? 'Sending…' : 'Send to Glasses'}
                  </button>
                  <div style={{ flex: 1 }} />
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={handleDeleteOpen}
                    style={{ color: 'var(--red)' }}
                    title="Delete this note from Obsidian"
                  >
                    <IconTrash /> Delete
                  </button>
                </div>

                <div style={{ fontSize: 11, color: 'var(--muted)', marginTop: 8 }}>
                  ⌘S to save · ⌘↵ to send to glasses
                </div>
              </div>
            ) : (
              <div style={{
                height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'var(--muted)', fontSize: 13, paddingTop: 60,
              }}>
                Select a note to open it
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function IconSearch() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <line x1="21" y1="21" x2="16.65" y2="16.65" />
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
