import { useRef, useState } from 'react'
import { api } from '../api'

// ── Storage keys ─────────────────────────────────────────────────────────────
const SUBMODE_KEY = 'evenconnect_send_submode'
const BG_KEY      = 'evenconnect_compose_default_bg'
const NOTES_KEY   = 'evenconnect_notes'
const MAX_CHARS   = 2000

// ── Layer helpers ─────────────────────────────────────────────────────────────
const POS_GRID = [
  ['top-left',    'top-center',    'top-right'],
  ['middle-left', 'middle-center', 'middle-right'],
  ['bottom-left', 'bottom-center', 'bottom-right'],
]
const POS_ARROW = {
  'top-left': '↖', 'top-center': '↑', 'top-right': '↗',
  'middle-left': '←', 'middle-center': '·', 'middle-right': '→',
  'bottom-left': '↙', 'bottom-center': '↓', 'bottom-right': '↘',
}

let _id = 0
const newTextLayer  = () => ({ id: ++_id, type: 'text',  text: '', position: 'bottom-left',   size: 14, color: 'light', padding: 14, z: 1 })
const newImageLayer = () => ({ id: ++_id, type: 'image', imageData: null, position: 'middle-center', z: 1 })

const toApiTextBlocks  = (layers) => layers.filter(l => l.type === 'text'  && l.text.trim()).map(({ text, position, size, color, padding, z }) => ({ text, position, size, color, padding, z }))
const toApiImageLayers = (layers) => layers.filter(l => l.type === 'image' && l.imageData).map(({ imageData, position, z }) => ({ imageData: imageData.split(',')[1], position, z }))

function loadNotes()         { try { return JSON.parse(localStorage.getItem(NOTES_KEY) || '[]') } catch { return [] } }
function persistNotes(notes) { localStorage.setItem(NOTES_KEY, JSON.stringify(notes)) }
function zLabel(z)           { return z > 0 ? `+${z}` : `${z}` }

// ── Root tab ──────────────────────────────────────────────────────────────────
export default function SendTab({ status, addToast, addLog }) {
  const [submode, setSubmode] = useState(() => localStorage.getItem(SUBMODE_KEY) || 'text')
  // Lazy-mount sections so internal state survives sub-mode switches
  const [visitedSub, setVisitedSub] = useState(() => new Set([localStorage.getItem(SUBMODE_KEY) || 'text']))

  const switchSubmode = (m) => {
    setSubmode(m)
    setVisitedSub(v => new Set([...v, m]))
    localStorage.setItem(SUBMODE_KEY, m)
  }

  return (
    <div className="tab-panel">
      <div className="tab-title">Send</div>
      <div className="mode-toggle" style={{ marginBottom: 16 }}>
        <button className={`mode-btn ${submode === 'text'    ? 'active' : ''}`} onClick={() => switchSubmode('text')}>Text</button>
        <button className={`mode-btn ${submode === 'compose' ? 'active' : ''}`} onClick={() => switchSubmode('compose')}>Compose</button>
      </div>

      {visitedSub.has('text') && (
        <div style={{ display: submode === 'text' ? 'contents' : 'none' }}>
          <TextSection status={status} addToast={addToast} />
        </div>
      )}
      {visitedSub.has('compose') && (
        <div style={{ display: submode === 'compose' ? 'contents' : 'none' }}>
          <ComposeSection status={status} addToast={addToast} addLog={addLog} />
        </div>
      )}
    </div>
  )
}

// ── Text section ──────────────────────────────────────────────────────────────
function TextSection({ status, addToast }) {
  const [text, setText]               = useState('')
  const [sending, setSending]         = useState(false)
  const [notes, setNotes]             = useState(loadNotes)
  const [saveHeading, setSaveHeading] = useState('')
  const [showSaveForm, setShowSaveForm] = useState(false)
  const textareaRef = useRef(null)
  const headingRef  = useRef(null)

  const handlePaste = async () => {
    try { const clip = await navigator.clipboard.readText(); setText(p => p + clip); textareaRef.current?.focus() }
    catch { addToast('Clipboard access denied — use Ctrl+V', 'error') }
  }

  const handleSend = async () => {
    if (!text.trim())      { addToast('Nothing to send', 'error'); return }
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    setSending(true)
    try { await api.sendText(text.trim()); addToast('Text sent to glasses', 'success') }
    catch (e) { addToast(e.message, 'error') }
    finally { setSending(false) }
  }

  const handleSaveNote = () => {
    if (!saveHeading.trim()) { headingRef.current?.focus(); return }
    const updated = [{ id: Date.now(), heading: saveHeading.trim(), text: text.trim() }, ...notes]
    setNotes(updated); persistNotes(updated); setSaveHeading(''); setShowSaveForm(false)
    addToast('Note saved', 'success')
  }

  const lineCount = text ? text.split('\n').length : 0

  return (
    <>
      <div className="card">
        <div className="card-label">Message</div>
        <textarea ref={textareaRef} className="textarea"
          placeholder="Type or paste text to display on the glasses…"
          value={text} onChange={e => setText(e.target.value.slice(0, MAX_CHARS))}
          onKeyDown={e => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleSend() }}
          spellCheck={false} />
        <div className="text-meta">
          <span>{lineCount} line{lineCount !== 1 ? 's' : ''} · {text.length} / {MAX_CHARS} chars</span>
          <span style={{ fontSize: 11, color: 'var(--muted)' }}>⌘↵ to send</span>
        </div>
        <div className="btn-row">
          <button className="btn btn-ghost btn-sm" onClick={handlePaste}><IconClipboard /> Paste</button>
          <button className="btn btn-ghost btn-sm" onClick={() => setText('')} disabled={!text}>Clear</button>
          <button className="btn btn-ghost btn-sm" onClick={() => { setShowSaveForm(v => !v); setTimeout(() => headingRef.current?.focus(), 0) }} disabled={!text.trim()}>
            <IconBookmark /> Save
          </button>
          <button className="btn btn-primary" onClick={handleSend} disabled={sending || !status.connected || !text.trim()}
            title={!status.connected ? 'Connect to glasses first' : '⌘↵'}>
            {sending ? 'Sending…' : 'Send to Glasses'}
          </button>
        </div>
        {showSaveForm && (
          <div style={{ marginTop: 14, display: 'flex', gap: 8, alignItems: 'center' }}>
            <input ref={headingRef} className="note-heading-input" placeholder="Note heading…"
              value={saveHeading} onChange={e => setSaveHeading(e.target.value)} maxLength={80}
              onKeyDown={e => { if (e.key === 'Enter') handleSaveNote(); if (e.key === 'Escape') setShowSaveForm(false) }} />
            <button className="btn btn-primary btn-sm" onClick={handleSaveNote}>Save</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowSaveForm(false)}>Cancel</button>
          </div>
        )}
      </div>

      {!status.connected && <div style={{ color: 'var(--muted)', fontSize: 12 }}>Connect to glasses on the Home tab before sending.</div>}

      {notes.length > 0 && (
        <div className="card">
          <div className="card-label">Saved Notes</div>
          <div className="notes-list">
            {notes.map(note => (
              <div key={note.id} className="note-item">
                <div className="note-item-body" onClick={() => { setText(note.text.slice(0, MAX_CHARS)); addToast(`Loaded "${note.heading}"`, 'info'); textareaRef.current?.focus() }}>
                  <span className="note-heading">{note.heading}</span>
                  <span className="note-preview">{note.text.slice(0, 80)}{note.text.length > 80 ? '…' : ''}</span>
                </div>
                <button className="note-delete-btn" onClick={() => { const u = notes.filter(n => n.id !== note.id); setNotes(u); persistNotes(u) }} title="Delete"><IconTrash /></button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="card" style={{ color: 'var(--muted)', fontSize: 12, lineHeight: 1.7 }}>
        <div className="card-label">Display notes</div>
        Right tap = next page · Left tap = previous page. Text longer than one screen is split into pages automatically.
      </div>
    </>
  )
}

// ── Compose section ───────────────────────────────────────────────────────────
function ComposeSection({ status, addToast, addLog }) {
  const [bg, setBg]     = useState(() => { try { return localStorage.getItem(BG_KEY) || null } catch { return null } })
  const [bgZ, setBgZ]   = useState(0)
  const [layers, setLayers] = useState([newTextLayer()])

  const [preview, setPreview]           = useState(null)
  const [stereoPreview, setStereoPreview] = useState(null)
  const [previewing, setPreviewing]     = useState(false)
  const [sending, setSending]           = useState(false)
  const [stereoSending, setStereoSending] = useState(false)
  const [bgDrag, setBgDrag]             = useState(false)
  const bgFileRef   = useRef(null)

  const b64 = (url) => (url ? url.split(',')[1] : '')
  const hasStereoDepth = bgZ !== 0 || layers.some(l => l.z !== 0)
  const resetPreviews  = () => { setPreview(null); setStereoPreview(null) }

  // ── Background ──────────────────────────────────────────────────────────────
  const loadBg = (file) => {
    if (!file?.type.startsWith('image/')) { addToast('Image files only', 'error'); return }
    const reader = new FileReader()
    reader.onload = e => { setBg(e.target.result); resetPreviews() }
    reader.readAsDataURL(file)
  }

  const setAsDefaultBg = () => {
    if (!bg) return
    try { localStorage.setItem(BG_KEY, bg); addToast('Default background saved', 'success') }
    catch { addToast('Image too large to save as default', 'error') }
  }

  const clearDefaultBg = () => { localStorage.removeItem(BG_KEY); setBg(null); setBgZ(0); resetPreviews(); addToast('Default background cleared', 'success') }
  const clearBg        = () => { setBg(null); setBgZ(0); resetPreviews() }

  // ── Layer management ────────────────────────────────────────────────────────
  const updateLayer = (id, patch) => { setLayers(ls => ls.map(l => l.id === id ? { ...l, ...patch } : l)); resetPreviews() }
  const removeLayer = (id)        => { setLayers(ls => ls.filter(l => l.id !== id)); resetPreviews() }
  const moveLayer   = (idx, dir)  => {
    setLayers(ls => { const n = [...ls]; const to = idx + dir; if (to < 0 || to >= n.length) return ls; [n[idx], n[to]] = [n[to], n[idx]]; return n })
    resetPreviews()
  }

  const loadImageForLayer = (id, file) => {
    if (!file?.type.startsWith('image/')) { addToast('Image files only', 'error'); return }
    const reader = new FileReader()
    reader.onload = e => updateLayer(id, { imageData: e.target.result })
    reader.readAsDataURL(file)
  }

  // ── Actions ─────────────────────────────────────────────────────────────────
  const handlePreview = async () => {
    setPreviewing(true); setPreview(null)
    try {
      const { preview: p } = await api.previewCompose(b64(bg), toApiTextBlocks(layers), toApiImageLayers(layers))
      setPreview(p)
    } catch (e) { addToast(e.message, 'error'); addLog(`ERROR:compose:${e.message}`) }
    finally { setPreviewing(false) }
  }

  const handleSend = async () => {
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    setSending(true)
    const start = performance.now()
    try {
      await api.sendCompose(b64(bg), toApiTextBlocks(layers), toApiImageLayers(layers))
      const ms = Math.round(performance.now() - start)
      addToast(`Composed image sent (${ms}ms)`, 'success'); addLog(`INFO:compose:Sent — ${ms}ms`)
    } catch (e) { addToast(e.message, 'error'); addLog(`ERROR:compose:${e.message}`) }
    finally { setSending(false) }
  }

  const handleStereoPreview = async () => {
    setPreviewing(true); setStereoPreview(null)
    try {
      const result = await api.previewStereoCompose(b64(bg), bgZ, toApiTextBlocks(layers), toApiImageLayers(layers))
      setStereoPreview(result)
    } catch (e) { addToast(e.message, 'error'); addLog(`ERROR:compose:stereo preview — ${e.message}`) }
    finally { setPreviewing(false) }
  }

  const handleStereoSend = async () => {
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    setStereoSending(true)
    const start = performance.now()
    try {
      await api.sendStereoCompose(b64(bg), bgZ, toApiTextBlocks(layers), toApiImageLayers(layers))
      const ms = Math.round(performance.now() - start)
      addToast(`Stereo compose sent (${ms}ms)`, 'success'); addLog(`INFO:compose:Stereo sent — ${ms}ms`)
    } catch (e) { addToast(e.message, 'error'); addLog(`ERROR:compose:${e.message}`) }
    finally { setStereoSending(false) }
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Background */}
      <div className="card">
        <div className="card-label">Background (optional)</div>
        {!bg ? (
          <div className={`compose-bg-drop ${bgDrag ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setBgDrag(true) }} onDragLeave={() => setBgDrag(false)}
            onDrop={e => { e.preventDefault(); setBgDrag(false); loadBg(e.dataTransfer.files[0]) }}
            onClick={() => bgFileRef.current?.click()}>
            <span>Drop or click to add a background — leave empty for solid black</span>
            <input ref={bgFileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => loadBg(e.target.files[0])} />
          </div>
        ) : (
          <div className="compose-bg-preview">
            <img src={bg} alt="Background" />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8, flexWrap: 'wrap' }}>
              <span className="compose-ctrl-label" style={{ minWidth: 44 }}>Depth</span>
              <input type="range" className="param-slider" min={-5} max={5} step={1} value={bgZ}
                onChange={e => { setBgZ(parseInt(e.target.value, 10)); resetPreviews() }} />
              <span className="compose-ctrl-val" style={{ minWidth: 28 }} title="-5 = furthest · 0 = neutral · +5 = closest">
                {bgZ === 0 ? '0' : zLabel(bgZ)}
              </span>
              <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
                <button className="btn btn-ghost btn-sm" onClick={setAsDefaultBg}>Set as Default</button>
                <button className="btn btn-ghost btn-sm" onClick={clearDefaultBg}>Clear Default</button>
                <button className="btn btn-ghost btn-sm" onClick={clearBg}>Remove</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Layers */}
      <div className="card">
        <div className="compose-layers-header">
          <span className="card-label" style={{ marginBottom: 0 }}>Layers</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setLayers(ls => [...ls, newTextLayer()])}>+ Text</button>
            <button className="btn btn-ghost btn-sm" onClick={() => setLayers(ls => [...ls, newImageLayer()])}>+ Image</button>
          </div>
        </div>

        {layers.map((layer, idx) => (
          <div key={layer.id} className="compose-block">
            <div className="compose-block-header">
              <span className="compose-block-label">
                {layer.type === 'image' ? '🖼 ' : ''}Layer {idx + 1}
              </span>
              <div className="compose-block-actions">
                <button className="compose-reorder-btn" onClick={() => moveLayer(idx, -1)} disabled={idx === 0}>↑</button>
                <button className="compose-reorder-btn" onClick={() => moveLayer(idx, 1)} disabled={idx === layers.length - 1}>↓</button>
                <button className="compose-reorder-btn compose-remove-btn" onClick={() => removeLayer(layer.id)}>✕</button>
              </div>
            </div>

            {layer.type === 'text' ? (
              <TextLayerControls layer={layer} updateLayer={updateLayer} />
            ) : (
              <ImageLayerControls layer={layer} updateLayer={updateLayer} loadImageForLayer={loadImageForLayer} />
            )}
          </div>
        ))}
      </div>

      {/* Preview */}
      <div className="card">
        <div className="card-label">
          Preview — 576×136 mono
          {hasStereoDepth && <span style={{ marginLeft: 8, fontSize: 11, color: 'var(--accent)' }}>stereo depth active</span>}
        </div>
        {stereoPreview ? (
          <div className="image-preview-row stereo-pair" style={{ marginTop: 4 }}>
            <div className="preview-box"><img src={stereoPreview.left} alt="Left eye" /><div className="preview-label">Left eye</div></div>
            <div className="preview-box"><img src={stereoPreview.right} alt="Right eye" /><div className="preview-label">Right eye</div></div>
          </div>
        ) : (
          <div className="compose-preview-box">
            {preview ? <img src={preview} alt="Compose preview" className="compose-preview-img" />
                     : <div className="compose-preview-placeholder">Click Preview to render</div>}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="btn-row">
        <button className="btn btn-ghost btn-sm" onClick={handlePreview} disabled={previewing}>{previewing ? 'Rendering…' : 'Preview'}</button>
        {hasStereoDepth && <button className="btn btn-ghost btn-sm" onClick={handleStereoPreview} disabled={previewing}>Preview Stereo</button>}
        <button className="btn btn-primary" onClick={handleSend} disabled={sending || !status.connected}
          title={!status.connected ? 'Connect glasses first' : ''}>{sending ? 'Sending…' : 'Send to Glasses'}</button>
        {hasStereoDepth && <button className="btn btn-primary" onClick={handleStereoSend} disabled={stereoSending || !status.connected}
          title={!status.connected ? 'Connect glasses first' : ''}>{stereoSending ? 'Sending…' : 'Send Stereo'}</button>}
      </div>
      {!status.connected && <div style={{ marginTop: 10, color: 'var(--muted)', fontSize: 12 }}>Connect to glasses on the Home tab before sending.</div>}
    </>
  )
}

// ── Text layer controls ───────────────────────────────────────────────────────
function TextLayerControls({ layer, updateLayer }) {
  return (
    <>
      <textarea className="textarea compose-textarea" placeholder="Enter text…" value={layer.text} rows={2}
        onChange={e => updateLayer(layer.id, { text: e.target.value })} />
      <div className="compose-controls">
        <div className="compose-pos-group">
          <div className="compose-pos-label">Position</div>
          <div className="compose-pos-grid">
            {POS_GRID.map((row, ri) => (
              <div key={ri} className="compose-pos-row">
                {row.map(pos => (
                  <button key={pos} className={`compose-pos-btn ${layer.position === pos ? 'active' : ''}`}
                    onClick={() => updateLayer(layer.id, { position: pos })} title={pos}>
                    {POS_ARROW[pos]}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className="compose-right-controls">
          <SliderRow label="Size"  value={layer.size}    min={10} max={40} onChange={v => updateLayer(layer.id, { size: v })}    suffix="px" />
          <SliderRow label="Pad"   value={layer.padding} min={0}  max={30} onChange={v => updateLayer(layer.id, { padding: v })} suffix="px" />
          <SliderRow label="Depth" value={layer.z}       min={-5} max={5}  onChange={v => updateLayer(layer.id, { z: v })}
            displayValue={layer.z === 0 ? '0' : (layer.z > 0 ? `+${layer.z}` : `${layer.z}`)}
            title="-5 = furthest · 0 = screen plane · +5 = closest" />
          <div className="compose-color-row">
            <span className="compose-ctrl-label">Ink</span>
            <div className="compose-color-toggle">
              <button className={`compose-color-btn ${layer.color === 'light' ? 'active' : ''}`} onClick={() => updateLayer(layer.id, { color: 'light' })}>Light</button>
              <button className={`compose-color-btn ${layer.color === 'dark'  ? 'active' : ''}`} onClick={() => updateLayer(layer.id, { color: 'dark'  })}>Dark</button>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

// ── Image layer controls ──────────────────────────────────────────────────────
function ImageLayerControls({ layer, updateLayer, loadImageForLayer }) {
  const fileRef = useRef(null)

  return (
    <>
      {!layer.imageData ? (
        <div className="compose-bg-drop" style={{ minHeight: 60 }}
          onDragOver={e => e.preventDefault()}
          onDrop={e => { e.preventDefault(); loadImageForLayer(layer.id, e.dataTransfer.files[0]) }}
          onClick={() => fileRef.current?.click()}>
          <span style={{ fontSize: 12 }}>Drop or click to load image</span>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => loadImageForLayer(layer.id, e.target.files[0])} />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap' }}>
          <img src={layer.imageData} alt="Layer" style={{ height: 48, objectFit: 'contain', border: '1px solid var(--border)', borderRadius: 4 }} />
          <button className="btn btn-ghost btn-sm" onClick={() => { updateLayer(layer.id, { imageData: null }); fileRef.current && (fileRef.current.value = '') }}>Replace</button>
          <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={e => loadImageForLayer(layer.id, e.target.files[0])} />
        </div>
      )}
      <div className="compose-controls" style={{ marginTop: 8 }}>
        <div className="compose-pos-group">
          <div className="compose-pos-label">Position</div>
          <div className="compose-pos-grid">
            {POS_GRID.map((row, ri) => (
              <div key={ri} className="compose-pos-row">
                {row.map(pos => (
                  <button key={pos} className={`compose-pos-btn ${layer.position === pos ? 'active' : ''}`}
                    onClick={() => updateLayer(layer.id, { position: pos })} title={pos}>
                    {POS_ARROW[pos]}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <button className={`compose-color-btn ${layer.position === 'fill' ? 'active' : ''}`}
            style={{ marginTop: 6, width: '100%' }} onClick={() => updateLayer(layer.id, { position: 'fill' })}>
            Fill
          </button>
        </div>
        <div className="compose-right-controls">
          <SliderRow label="Depth" value={layer.z} min={-5} max={5} onChange={v => updateLayer(layer.id, { z: v })}
            displayValue={layer.z === 0 ? '0' : (layer.z > 0 ? `+${layer.z}` : `${layer.z}`)}
            title="-5 = furthest · 0 = screen plane · +5 = closest" />
        </div>
      </div>
    </>
  )
}

// ── Shared slider row ─────────────────────────────────────────────────────────
function SliderRow({ label, value, min, max, onChange, suffix = '', displayValue, title }) {
  return (
    <div className="compose-slider-row">
      <span className="compose-ctrl-label">{label}</span>
      <input type="range" className="param-slider" min={min} max={max} step={1} value={value}
        onChange={e => onChange(parseInt(e.target.value, 10))} />
      <span className="compose-ctrl-val" title={title}>
        {displayValue !== undefined ? displayValue : `${value}${suffix}`}
      </span>
    </div>
  )
}

// ── Icons ─────────────────────────────────────────────────────────────────────
function IconClipboard() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /><rect x="8" y="2" width="8" height="4" rx="1" ry="1" /></svg>
}
function IconBookmark() {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /></svg>
}
function IconTrash() {
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="3 6 5 6 21 6" /><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" /><path d="M10 11v6M14 11v6" /><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" /></svg>
}
