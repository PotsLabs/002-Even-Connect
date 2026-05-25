import { useRef, useState } from 'react'
import { api } from '../api'

const POS_GRID = [
  ['top-left', 'top-center', 'top-right'],
  ['middle-left', 'middle-center', 'middle-right'],
  ['bottom-left', 'bottom-center', 'bottom-right'],
]
const POS_ARROW = {
  'top-left': '↖', 'top-center': '↑', 'top-right': '↗',
  'middle-left': '←', 'middle-center': '·', 'middle-right': '→',
  'bottom-left': '↙', 'bottom-center': '↓', 'bottom-right': '↘',
}

let _id = 0
const newBlock = () => ({
  id: ++_id,
  text: '',
  position: 'bottom-left',
  size: 18,
  color: 'light',
  padding: 6,
})

const toApiBlocks = (blocks) =>
  blocks
    .filter(b => b.text.trim())
    .map(({ text, position, size, color, padding }) => ({ text, position, size, color, padding }))

export default function ComposeTab({ status, addToast, addLog }) {
  const [bg, setBg]           = useState(null)
  const [blocks, setBlocks]   = useState([newBlock()])
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [sending, setSending] = useState(false)
  const [bgDrag, setBgDrag]   = useState(false)
  const fileRef = useRef(null)

  const b64 = (url) => (url ? url.split(',')[1] : '')

  // ── Background ────────────────────────────────────────────────────────────

  const loadBg = (file) => {
    if (!file || !file.type.startsWith('image/')) { addToast('Image files only', 'error'); return }
    const reader = new FileReader()
    reader.onload = (e) => { setBg(e.target.result); setPreview(null) }
    reader.readAsDataURL(file)
  }

  const onBgDrop = (e) => {
    e.preventDefault(); setBgDrag(false)
    loadBg(e.dataTransfer.files[0])
  }

  // ── Blocks ────────────────────────────────────────────────────────────────

  const addBlock = () => setBlocks(bs => [...bs, newBlock()])

  const updateBlock = (id, patch) => {
    setBlocks(bs => bs.map(b => b.id === id ? { ...b, ...patch } : b))
    setPreview(null)
  }

  const removeBlock = (id) => {
    setBlocks(bs => bs.filter(b => b.id !== id))
    setPreview(null)
  }

  const moveBlock = (idx, dir) => {
    setBlocks(bs => {
      const next = [...bs]
      const to = idx + dir
      if (to < 0 || to >= next.length) return bs
      ;[next[idx], next[to]] = [next[to], next[idx]]
      return next
    })
    setPreview(null)
  }

  // ── Actions ───────────────────────────────────────────────────────────────

  const handlePreview = async () => {
    setPreviewing(true)
    setPreview(null)
    try {
      const { preview: p } = await api.previewCompose(b64(bg), toApiBlocks(blocks))
      setPreview(p)
    } catch (e) {
      addToast(e.message, 'error')
      addLog(`ERROR:compose:${e.message}`)
    } finally {
      setPreviewing(false)
    }
  }

  const handleSend = async () => {
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    setSending(true)
    const start = performance.now()
    try {
      await api.sendCompose(b64(bg), toApiBlocks(blocks))
      const ms = Math.round(performance.now() - start)
      addToast(`Composed image sent (${ms}ms)`, 'success')
      addLog(`INFO:compose:Sent — ${ms}ms`)
    } catch (e) {
      addToast(e.message, 'error')
      addLog(`ERROR:compose:${e.message}`)
    } finally {
      setSending(false)
    }
  }

  const handleAddToQueue = async (addToImageQueue) => {
    try {
      const { id, preview: thumb } = await api.precomputeCompose(b64(bg), toApiBlocks(blocks))
      addToImageQueue({ id, original: thumb, mode: 'standard', stereo: {}, precomputed: 'ready' })
      addToast('Composition added to queue', 'success')
      addLog(`INFO:compose:Precomputed and queued (id ${id.slice(0, 8)}…)`)
    } catch (e) {
      addToast(e.message, 'error')
      addLog(`ERROR:compose:${e.message}`)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="tab-panel">
      <div className="tab-title">Compose</div>

      {/* Background */}
      <div className="card">
        <div className="card-label">Background Image (optional)</div>
        {!bg ? (
          <div
            className={`compose-bg-drop ${bgDrag ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setBgDrag(true) }}
            onDragLeave={() => setBgDrag(false)}
            onDrop={onBgDrop}
            onClick={() => fileRef.current?.click()}
          >
            <span>Drop or click to add a background — leave empty for solid black</span>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={e => loadBg(e.target.files[0])} />
          </div>
        ) : (
          <div className="compose-bg-preview">
            <img src={bg} alt="Background" />
            <button className="btn btn-ghost btn-sm compose-bg-clear"
              onClick={() => { setBg(null); setPreview(null) }}>
              Clear
            </button>
          </div>
        )}
      </div>

      {/* Text layers */}
      <div className="card">
        <div className="compose-layers-header">
          <span className="card-label" style={{ marginBottom: 0 }}>Text Layers</span>
          <button className="btn btn-ghost btn-sm" onClick={addBlock}>+ Add Layer</button>
        </div>

        {blocks.map((block, idx) => (
          <div key={block.id} className="compose-block">
            <div className="compose-block-header">
              <span className="compose-block-label">Layer {idx + 1}</span>
              <div className="compose-block-actions">
                <button className="compose-reorder-btn" onClick={() => moveBlock(idx, -1)} disabled={idx === 0} title="Move up">↑</button>
                <button className="compose-reorder-btn" onClick={() => moveBlock(idx, 1)} disabled={idx === blocks.length - 1} title="Move down">↓</button>
                <button className="compose-reorder-btn compose-remove-btn" onClick={() => removeBlock(block.id)} title="Remove">✕</button>
              </div>
            </div>

            <textarea
              className="textarea compose-textarea"
              placeholder="Enter text… (Enter for new line)"
              value={block.text}
              rows={2}
              onChange={e => updateBlock(block.id, { text: e.target.value })}
            />

            <div className="compose-controls">
              {/* 3×3 position grid */}
              <div className="compose-pos-group">
                <div className="compose-pos-label">Position</div>
                <div className="compose-pos-grid">
                  {POS_GRID.map((row, ri) => (
                    <div key={ri} className="compose-pos-row">
                      {row.map(pos => (
                        <button
                          key={pos}
                          className={`compose-pos-btn ${block.position === pos ? 'active' : ''}`}
                          onClick={() => updateBlock(block.id, { position: pos })}
                          title={pos}
                        >
                          {POS_ARROW[pos]}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
              </div>

              {/* Size + color */}
              <div className="compose-right-controls">
                <div className="compose-slider-row">
                  <span className="compose-ctrl-label">Size</span>
                  <input type="range" className="param-slider" min={10} max={40} step={1}
                    value={block.size}
                    onChange={e => updateBlock(block.id, { size: parseInt(e.target.value, 10) })} />
                  <span className="compose-ctrl-val">{block.size}px</span>
                </div>

                <div className="compose-slider-row">
                  <span className="compose-ctrl-label">Pad</span>
                  <input type="range" className="param-slider" min={0} max={20} step={1}
                    value={block.padding}
                    onChange={e => updateBlock(block.id, { padding: parseInt(e.target.value, 10) })} />
                  <span className="compose-ctrl-val">{block.padding}px</span>
                </div>

                <div className="compose-color-row">
                  <span className="compose-ctrl-label">Ink</span>
                  <div className="compose-color-toggle">
                    <button
                      className={`compose-color-btn ${block.color === 'light' ? 'active' : ''}`}
                      onClick={() => updateBlock(block.id, { color: 'light' })}
                    >Light</button>
                    <button
                      className={`compose-color-btn ${block.color === 'dark' ? 'active' : ''}`}
                      onClick={() => updateBlock(block.id, { color: 'dark' })}
                    >Dark</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Preview */}
      <div className="card">
        <div className="card-label">Preview — 576×136 mono</div>
        <div className="compose-preview-box">
          {preview
            ? <img src={preview} alt="Compose preview" className="compose-preview-img" />
            : <div className="compose-preview-placeholder">Click Preview to render</div>
          }
        </div>
      </div>

      {/* Actions */}
      <div className="btn-row">
        <button className="btn btn-ghost btn-sm" onClick={handlePreview} disabled={previewing}>
          {previewing ? 'Rendering…' : 'Preview'}
        </button>
        <button className="btn btn-primary" onClick={handleSend}
          disabled={sending || !status.connected}
          title={!status.connected ? 'Connect to glasses first' : ''}>
          {sending ? 'Sending…' : 'Send to Glasses'}
        </button>
      </div>

      {!status.connected && (
        <div style={{ marginTop: 10, color: 'var(--muted)', fontSize: 12 }}>
          Connect to glasses on the Home tab before sending.
        </div>
      )}
    </div>
  )
}
