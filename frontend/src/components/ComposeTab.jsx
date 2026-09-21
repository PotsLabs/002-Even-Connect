import { useRef, useState, useEffect } from 'react'
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
const newTextLayer = () => ({
  id: ++_id,
  type: 'text',
  text: '',
  position: 'bottom-left',
  size: 18,
  padding: 6,
  z: 0,
})

const newImageLayer = () => ({
  id: ++_id,
  type: 'image',
  imageData: null,
  position: 'middle-center',
  z: 0,
})

const toApiLayers = (layers) =>
  layers
    .filter(l => {
      if (l.type === 'text') return l.text?.trim()
      if (l.type === 'image') return l.imageData
      return false
    })
    .map(l => {
      if (l.type === 'text') {
        return { type: 'text', text: l.text, position: l.position, size: l.size, padding: l.padding, z: l.z }
      } else {
        const base64 = l.imageData.includes(',') ? l.imageData.split(',')[1] : l.imageData
        return { type: 'image', imageData: base64, position: l.position, z: l.z }
      }
    })

export default function ComposeTab({ status, addToast, addLog }) {
  const [layers, setLayers] = useState([newTextLayer()])
  const [preview, setPreview] = useState(null)
  const [previewing, setPreviewing] = useState(false)
  const [sending, setSending] = useState(false)
  const [savedLayouts, setSavedLayouts] = useState([])
  const [saveName, setSaveName] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    loadSavedLayouts()
  }, [])

  const loadSavedLayouts = async () => {
    try {
      const result = await api.listLayouts()
      setSavedLayouts(result.layouts || [])
    } catch (e) {
      console.error('Failed to load layouts:', e)
    }
  }

  const handleSaveLayout = async () => {
    if (!saveName.trim()) {
      addToast('Enter a name for this layout', 'error')
      return
    }
    setSaving(true)
    try {
      const payload = { layers: toApiLayers(layers) }
      await api.saveLayout(saveName, payload.layers)
      addToast(`Layout saved: ${saveName}`, 'success')
      setSaveName('')
      await loadSavedLayouts()
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleLoadLayout = async (layoutId) => {
    try {
      const layout = await api.getLayout(layoutId)
      const loadedLayers = layout.layers.map((l, idx) => ({
        id: ++_id,
        ...l
      }))
      setLayers(loadedLayers)
      setPreview(null)
      addToast(`Loaded: ${layout.name}`, 'success')
    } catch (e) {
      addToast(e.message, 'error')
    }
  }

  const handleDeleteLayout = async (layoutId, name) => {
    if (!window.confirm(`Delete layout "${name}"?`)) return
    try {
      await api.deleteLayout(layoutId)
      addToast(`Deleted: ${name}`, 'success')
      await loadSavedLayouts()
    } catch (e) {
      addToast(e.message, 'error')
    }
  }

  // ── Layers (unified) ──────────────────────────────────────────────────────
  const addTextLayer = () => setLayers(ls => [...ls, newTextLayer()])
  const addImageLayer = () => setLayers(ls => [...ls, newImageLayer()])

  const updateLayer = (id, patch) => {
    setLayers(ls => ls.map(l => l.id === id ? { ...l, ...patch } : l))
    setPreview(null)
  }

  const removeLayer = (id) => {
    setLayers(ls => ls.filter(l => l.id !== id))
    setPreview(null)
  }

  const moveLayer = (idx, dir) => {
    setLayers(ls => {
      const next = [...ls]
      const to = idx + dir
      if (to < 0 || to >= next.length) return ls
      ;[next[idx], next[to]] = [next[to], next[idx]]
      return next
    })
    setPreview(null)
  }

  const loadImageForLayer = (id, file) => {
    if (!file?.type.startsWith('image/')) { addToast('Image files only', 'error'); return }
    const reader = new FileReader()
    reader.onload = (e) => updateLayer(id, { imageData: e.target.result })
    reader.readAsDataURL(file)
  }

  // ── Actions ───────────────────────────────────────────────────────────────
  const handlePreview = async () => {
    const validLayers = layers.filter(l => {
      if (l.type === 'text') return l.text?.trim()
      if (l.type === 'image') return l.imageData
      return false
    })

    if (validLayers.length === 0) {
      addToast('Add text or image layers to preview', 'error')
      return
    }

    setPreviewing(true)
    try {
      const payload = { layers: toApiLayers(layers) }
      const result = await api.previewCompose(payload)
      setPreview(result)
      addToast(`Preview rendered: ${result.layers} layers`, 'info')
    } catch (e) {
      const errorMsg = e?.message || String(e) || 'Unknown error'
      addToast(`Preview failed: ${errorMsg}`, 'error')
    } finally {
      setPreviewing(false)
    }
  }

  const handleSend = async () => {
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }

    const validLayers = layers.filter(l => {
      if (l.type === 'text') return l.text?.trim()
      if (l.type === 'image') return l.imageData
      return false
    })

    if (validLayers.length === 0) {
      addToast('Add text or image layers to compose', 'error'); return
    }
    setSending(true)
    const start = performance.now()
    try {
      const payload = { layers: toApiLayers(layers) }
      const response = await api.sendCompose(payload)
      const ms = Math.round(performance.now() - start)
      addToast(`Composed image sent (${ms}ms)`, 'success')
      addLog(`INFO:compose:Sent ${response.layers} layers — ${ms}ms`)
    } catch (e) {
      const errorMsg = e?.message || String(e) || 'Unknown error'
      addToast(errorMsg, 'error')
      addLog(`ERROR:compose:${errorMsg}`)
    } finally {
      setSending(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="tab-panel">
      <div className="tab-title">Compose</div>

      {/* Unified Layers */}
      <div className="card">
        <div className="compose-layers-header">
          <span className="card-label" style={{ marginBottom: 0 }}>Layers</span>
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-ghost btn-sm" onClick={addTextLayer}>+ Text</button>
            <button className="btn btn-ghost btn-sm" onClick={addImageLayer}>+ Image</button>
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
              <>
                <textarea
                  className="textarea compose-textarea"
                  placeholder="Enter text…"
                  value={layer.text}
                  rows={2}
                  onChange={e => updateLayer(layer.id, { text: e.target.value })}
                />

                <div className="compose-controls">
                  <div className="compose-pos-group">
                    <div className="compose-pos-label">Position</div>
                    <div className="compose-pos-grid">
                      {POS_GRID.map((row, ri) => (
                        <div key={ri} className="compose-pos-row">
                          {row.map(pos => (
                            <button
                              key={pos}
                              className={`compose-pos-btn ${layer.position === pos ? 'active' : ''}`}
                              onClick={() => updateLayer(layer.id, { position: pos })}
                              title={pos}
                            >
                              {POS_ARROW[pos]}
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="compose-right-controls">
                    <div className="compose-slider-row">
                      <span className="compose-ctrl-label">Size</span>
                      <input type="range" className="param-slider" min={10} max={40} step={1}
                        value={layer.size}
                        onChange={e => updateLayer(layer.id, { size: parseInt(e.target.value, 10) })} />
                      <span className="compose-ctrl-val">{layer.size}px</span>
                    </div>

                    <div className="compose-slider-row">
                      <span className="compose-ctrl-label">Pad</span>
                      <input type="range" className="param-slider" min={0} max={20} step={1}
                        value={layer.padding}
                        onChange={e => updateLayer(layer.id, { padding: parseInt(e.target.value, 10) })} />
                      <span className="compose-ctrl-val">{layer.padding}px</span>
                    </div>

                    <div className="compose-slider-row">
                      <span className="compose-ctrl-label">Depth</span>
                      <input type="range" className="param-slider" min={-5} max={5} step={1}
                        value={layer.z}
                        onChange={e => updateLayer(layer.id, { z: parseInt(e.target.value, 10) })} />
                      <span className="compose-ctrl-val">
                        {layer.z === 0 ? '0' : (layer.z > 0 ? `+${layer.z}` : `${layer.z}`)}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                {!layer.imageData ? (
                  <div className="compose-bg-drop" style={{ minHeight: 60 }}
                    onDragOver={e => e.preventDefault()}
                    onDrop={e => { e.preventDefault(); loadImageForLayer(layer.id, e.dataTransfer.files[0]) }}
                    onClick={() => {
                      const input = document.createElement('input')
                      input.type = 'file'
                      input.accept = 'image/*'
                      input.onchange = (e) => loadImageForLayer(layer.id, e.target.files[0])
                      input.click()
                    }}>
                    <span style={{ fontSize: 12 }}>Drop or click to load image</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', gap: 10, alignItems: 'flex-start', flexWrap: 'wrap', marginBottom: 10 }}>
                    <img src={layer.imageData} alt="Layer" style={{ height: 48, objectFit: 'contain', border: '1px solid var(--border)', borderRadius: 4 }} />
                    <button className="btn btn-ghost btn-sm" onClick={() => updateLayer(layer.id, { imageData: null })}>Replace</button>
                  </div>
                )}

                <div className="compose-controls" style={{ marginTop: layer.imageData ? 0 : 8 }}>
                  <div className="compose-pos-group">
                    <div className="compose-pos-label">Position</div>
                    <div className="compose-pos-grid">
                      {POS_GRID.map((row, ri) => (
                        <div key={ri} className="compose-pos-row">
                          {row.map(pos => (
                            <button
                              key={pos}
                              className={`compose-pos-btn ${layer.position === pos ? 'active' : ''}`}
                              onClick={() => updateLayer(layer.id, { position: pos })}
                              title={pos}
                            >
                              {POS_ARROW[pos]}
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="compose-right-controls">
                    <div className="compose-slider-row">
                      <span className="compose-ctrl-label">Depth</span>
                      <input type="range" className="param-slider" min={-5} max={5} step={1}
                        value={layer.z}
                        onChange={e => updateLayer(layer.id, { z: parseInt(e.target.value, 10) })} />
                      <span className="compose-ctrl-val">
                        {layer.z === 0 ? '0' : (layer.z > 0 ? `+${layer.z}` : `${layer.z}`)}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Save Layout */}
      <div className="card">
        <div className="card-label">Save Layout</div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
          <input
            type="text"
            placeholder="Layout name…"
            value={saveName}
            onChange={e => setSaveName(e.target.value)}
            onKeyPress={e => e.key === 'Enter' && handleSaveLayout()}
            style={{ flex: 1, padding: '6px 8px', border: '1px solid var(--border)', borderRadius: 4 }}
          />
          <button className="btn btn-ghost btn-sm" onClick={handleSaveLayout} disabled={saving || !saveName.trim()}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      {/* Saved Layouts */}
      {savedLayouts.length > 0 && (
        <div className="card">
          <div className="card-label">Saved Layouts</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {savedLayouts.map(layout => (
              <div key={layout.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 8, backgroundColor: 'var(--bg-secondary)', borderRadius: 4 }}>
                <div>
                  <div style={{ fontWeight: 500 }}>{layout.name}</div>
                  <div style={{ fontSize: 11, color: 'var(--muted)' }}>{layout.layers?.length || 0} layer{(layout.layers?.length || 0) !== 1 ? 's' : ''}</div>
                </div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleLoadLayout(layout.id)}>
                    Load
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleDeleteLayout(layout.id, layout.name)} style={{ color: 'var(--danger)' }}>
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Preview */}
      <div className="card">
        <div className="card-label">Preview — 576×136 mono (stereo pair)</div>
        {preview ? (
          <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Left Eye</div>
              <img src={preview.left} alt="Left eye" style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 4 }} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Right Eye</div>
              <img src={preview.right} alt="Right eye" style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 4 }} />
            </div>
          </div>
        ) : (
          <div className="compose-preview-box">
            <div className="compose-preview-placeholder">Click Preview to render stereo pair</div>
          </div>
        )}
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
