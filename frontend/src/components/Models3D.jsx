import { useState, useEffect } from 'react'
import { api, apiUrl } from '../api'

export default function Models3D({ status, addToast, addLog }) {
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState(null)
  const [preview, setPreview] = useState(null)
  const [uploading, setUploading] = useState(false)
  const [rendering, setRendering] = useState(false)
  const [sending, setSending] = useState(false)

  // Render controls
  const [offsetX, setOffsetX] = useState(0)  // Translation X (-100 to +100)
  const [offsetY, setOffsetY] = useState(0)  // Translation Y (-50 to +50)
  const [z, setZ] = useState(0)
  const [fov, setFov] = useState(60)
  const [distance, setDistance] = useState(300)

  useEffect(() => {
    loadModels()
    // Load first model (arrow_forward) by default
    setSelectedModel('arrow_forward')
  }, [])

  const loadModels = async () => {
    try {
      const result = await api.listModels()
      setModels(result.models || [])
    } catch (e) {
      addToast('Failed to load models', 'error')
    }
  }

  const handleUpload = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(apiUrl('/models'), {
        method: 'POST',
        body: formData,
      })
      const data = await response.json()

      if (!response.ok) throw new Error(data.detail || 'Upload failed')

      addToast(`Model uploaded: ${data.name}`, 'success')
      await loadModels()
      setSelectedModel(data.id)
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  const handlePreview = async () => {
    if (!selectedModel) {
      addToast('Select a model first', 'error')
      return
    }

    setRendering(true)
    try {
      const result = await api.preview3DModel(selectedModel, {
        offsetX,
        offsetY,
        z,
        fov,
        distance,
      })
      setPreview(result)
      addToast('Preview rendered', 'success')
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setRendering(false)
    }
  }

  const handleSend = async () => {
    if (!status.connected) {
      addToast('Glasses not connected', 'error')
      return
    }

    if (!selectedModel) {
      addToast('Select a model first', 'error')
      return
    }

    setSending(true)
    try {
      const response = await api.send3DModel(selectedModel, {
        offsetX,
        offsetY,
        z,
        fov,
        distance,
      })
      addToast('3D model sent to glasses', 'success')
      addLog(`INFO:3d:Sent ${selectedModel}`)
    } catch (e) {
      addToast(e.message, 'error')
      addLog(`ERROR:3d:${e.message}`)
    } finally {
      setSending(false)
    }
  }

  const selectArrow = (modelId) => {
    setSelectedModel(modelId)
    setOffsetX(0)      // Reset translation
    setOffsetY(0)
    setPreview(null)
  }

  return (
    <div className="tab-panel">
      <div className="tab-title">3D Models</div>

      {/* Upload */}
      <div className="card">
        <div className="card-label">Upload OBJ Model</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="file"
            accept=".obj"
            onChange={handleUpload}
            disabled={uploading}
            style={{ flex: 1 }}
          />
          <span style={{ color: 'var(--muted)', fontSize: 12, padding: '6px 0' }}>
            {uploading ? 'Uploading…' : 'OBJ files only'}
          </span>
        </div>
      </div>

      {/* Arrow Presets */}
      <div className="card">
        <div className="card-label">Navigation Arrows</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 6 }}>
          <button
            className={`btn ${selectedModel === 'arrow_left' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => selectArrow('arrow_left')}
          >
            ⬅ Left
          </button>
          <button
            className={`btn ${selectedModel === 'arrow_forward' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => selectArrow('arrow_forward')}
          >
            ⬆ Forward
          </button>
          <button
            className={`btn ${selectedModel === 'arrow_right' ? 'btn-primary' : 'btn-ghost'}`}
            onClick={() => selectArrow('arrow_right')}
          >
            ⬅ Right
          </button>
        </div>
      </div>

      {/* Model Selection */}
      {models.length > 0 && (
        <div className="card">
          <div className="card-label">All Models ({models.length})</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 200, overflowY: 'auto' }}>
            {models.map(model => (
              <button
                key={model.id}
                onClick={() => selectArrow(model.id)}
                style={{
                  padding: 8,
                  backgroundColor: selectedModel === model.id ? 'var(--accent)' : 'var(--bg-secondary)',
                  border: 'none',
                  borderRadius: 4,
                  cursor: 'pointer',
                  textAlign: 'left',
                  fontSize: 13,
                }}
              >
                <div style={{ fontWeight: 500 }}>{model.name}</div>
                <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                  {(model.size / 1024).toFixed(1)} KB
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Render Controls */}
      {selectedModel && (
        <div className="card">
          <div className="card-label">Position & Depth</div>
          <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 12, padding: '6px 0 0 0' }}>
            ✓ Fixed view angle (20° top-down perspective)
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
            {/* Translation */}
            <div>
              <label style={{ fontSize: 12, color: 'var(--muted)' }}>Horizontal (X)</label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="range"
                  min="-100"
                  max="100"
                  step="1"
                  value={offsetX}
                  onChange={e => setOffsetX(parseFloat(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ minWidth: 35, textAlign: 'right', fontSize: 12 }}>
                  {offsetX > 0 ? '+' : ''}{offsetX}px
                </span>
              </div>
            </div>

            <div>
              <label style={{ fontSize: 12, color: 'var(--muted)' }}>Vertical (Y)</label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="range"
                  min="-50"
                  max="50"
                  step="1"
                  value={offsetY}
                  onChange={e => setOffsetY(parseFloat(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ minWidth: 35, textAlign: 'right', fontSize: 12 }}>
                  {offsetY > 0 ? '+' : ''}{offsetY}px
                </span>
              </div>
            </div>

            <div>
              <label style={{ fontSize: 12, color: 'var(--muted)' }}>Z-Depth</label>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <input
                  type="range"
                  min="-5"
                  max="5"
                  step="0.5"
                  value={z}
                  onChange={e => setZ(parseFloat(e.target.value))}
                  style={{ flex: 1 }}
                />
                <span style={{ minWidth: 30, textAlign: 'right', fontSize: 12 }}>{z > 0 ? '+' : ''}{z.toFixed(1)}</span>
              </div>
            </div>

            {/* Advanced: Camera */}
            <div>
              <label style={{ fontSize: 12, color: 'var(--muted)' }}>Camera Distance</label>
              <input
                type="range"
                min="100"
                max="500"
                step="10"
                value={distance}
                onChange={e => setDistance(parseFloat(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>

            <div>
              <label style={{ fontSize: 12, color: 'var(--muted)' }}>FOV</label>
              <input
                type="range"
                min="20"
                max="120"
                step="5"
                value={fov}
                onChange={e => setFov(parseFloat(e.target.value))}
                style={{ width: '100%' }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Preview */}
      {selectedModel && (
        <div className="card">
          <div className="card-label">Preview (Left/Right Stereo)</div>
          {preview ? (
            <div style={{ display: 'flex', gap: 12, marginTop: 10 }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Left Eye</div>
                <img src={preview.left} alt="Left" style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 4 }} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 6 }}>Right Eye</div>
                <img src={preview.right} alt="Right" style={{ width: '100%', border: '1px solid var(--border)', borderRadius: 4 }} />
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: 20, color: 'var(--muted)', fontSize: 12 }}>
              Click Preview to render stereo pair
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="btn-row">
        <button className="btn btn-ghost btn-sm" onClick={handlePreview} disabled={!selectedModel || rendering}>
          {rendering ? 'Rendering…' : 'Preview'}
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSend}
          disabled={!selectedModel || sending || !status.connected}
          title={!status.connected ? 'Connect to glasses first' : ''}
        >
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
