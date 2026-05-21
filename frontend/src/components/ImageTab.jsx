import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

const DEFAULT_STEREO = { maxDisparity: 6, blurRadius: 3, invertDepth: false }

export default function ImageTab({ status, addToast }) {
  const [original, setOriginal]       = useState(null)
  const [mode, setMode]               = useState('standard')   // 'standard' | 'stereo'
  const [bmpPreview, setBmpPreview]   = useState(null)         // standard: string; stereo: {left, right}
  const [stereo, setStereo]           = useState(DEFAULT_STEREO)
  const [drag, setDrag]               = useState(false)
  const [previewing, setPreviewing]   = useState(false)
  const [sending, setSending]         = useState(false)
  const fileRef = useRef(null)

  const loadFile = useCallback((file) => {
    if (!file || !file.type.startsWith('image/')) {
      addToast('Please select an image file', 'error')
      return
    }
    const reader = new FileReader()
    reader.onload = (e) => { setOriginal(e.target.result); setBmpPreview(null) }
    reader.readAsDataURL(file)
  }, [addToast])

  useEffect(() => {
    const onPaste = (e) => {
      const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith('image/'))
      if (item) loadFile(item.getAsFile())
    }
    window.addEventListener('paste', onPaste)
    return () => window.removeEventListener('paste', onPaste)
  }, [loadFile])

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false)
    const file = e.dataTransfer.files[0]
    if (file) loadFile(file)
  }

  const b64 = (dataUrl) => dataUrl.split(',')[1]

  const handlePreview = async () => {
    if (!original) return
    setPreviewing(true)
    setBmpPreview(null)
    try {
      if (mode === 'stereo') {
        const result = await api.previewStereoBmp(b64(original), stereo)
        setBmpPreview(result)
      } else {
        const { preview } = await api.previewBmp(b64(original))
        setBmpPreview(preview)
      }
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setPreviewing(false)
    }
  }

  const handleSend = async () => {
    if (!original) return
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    setSending(true)
    try {
      if (mode === 'stereo') {
        await api.sendStereoImage(b64(original), stereo)
        addToast('Stereo image sent to glasses', 'success')
      } else {
        await api.sendImage(b64(original))
        addToast('Image sent to glasses', 'success')
      }
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSending(false)
    }
  }

  const handleClear = () => {
    setOriginal(null); setBmpPreview(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const setStereoParam = (key, val) => {
    setStereo(s => ({ ...s, [key]: val }))
    setBmpPreview(null)
  }

  const switchMode = (m) => { setMode(m); setBmpPreview(null) }

  return (
    <div className="tab-panel">
      <div className="tab-title">Image &amp; Bitmap</div>

      {!original ? (
        <div
          className={`drop-zone ${drag ? 'drag-over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
        >
          <IconImage />
          <p>Drop an image here, click to browse, or paste with Ctrl+V</p>
          <p style={{ fontSize: '11px', marginTop: 4 }}>
            PNG, JPG, BMP — will be resized to 576×136 monochrome
          </p>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => loadFile(e.target.files[0])}
          />
        </div>
      ) : (
        <>
          {/* Mode toggle */}
          <div className="mode-toggle">
            <button
              className={`mode-btn ${mode === 'standard' ? 'active' : ''}`}
              onClick={() => switchMode('standard')}
            >
              Standard
            </button>
            <button
              className={`mode-btn ${mode === 'stereo' ? 'active' : ''}`}
              onClick={() => switchMode('stereo')}
            >
              Stereo 3D
            </button>
          </div>

          {/* Stereo depth tuning */}
          {mode === 'stereo' && (
            <div className="stereo-params">
              <div className="stereo-params-title">Depth Parameters</div>

              <ParamSlider
                label="Max Disparity"
                value={stereo.maxDisparity}
                min={1} max={20} step={1}
                onChange={v => setStereoParam('maxDisparity', v)}
                hint="px — how far foreground floats"
              />
              <ParamSlider
                label="Blur Radius"
                value={stereo.blurRadius}
                min={0} max={10} step={0.5}
                onChange={v => setStereoParam('blurRadius', v)}
                hint="depth map smoothing, higher = less fringing"
              />

              <div className="param-row">
                <span className="param-label">Invert Depth</span>
                <label className="toggle-switch">
                  <input
                    type="checkbox"
                    checked={stereo.invertDepth}
                    onChange={e => setStereoParam('invertDepth', e.target.checked)}
                  />
                  <span className="toggle-track" />
                </label>
                <span className="param-hint">dark = near (for point clouds / light backgrounds)</span>
              </div>
            </div>
          )}

          {/* Previews */}
          {mode === 'standard' ? (
            <div className="image-preview-row" style={{ marginTop: 16 }}>
              <PreviewBox src={original} label="Original" />
              <PreviewBox
                src={typeof bmpPreview === 'string' ? bmpPreview : null}
                label="Glasses view (576×136 mono)"
                placeholder="Click Preview BMP"
              />
            </div>
          ) : (
            <>
              <div className="image-preview-row" style={{ gridTemplateColumns: '1fr', marginTop: 16 }}>
                <PreviewBox src={original} label="Original" />
              </div>
              <div className="image-preview-row stereo-pair" style={{ marginTop: 8 }}>
                <PreviewBox
                  src={bmpPreview?.left ?? null}
                  label="Left eye"
                  placeholder="Click Preview to generate"
                />
                <PreviewBox
                  src={bmpPreview?.right ?? null}
                  label="Right eye"
                  placeholder="Click Preview to generate"
                />
              </div>
            </>
          )}

          <div className="btn-row" style={{ marginTop: 14 }}>
            <button className="btn btn-ghost btn-sm" onClick={handlePreview} disabled={previewing}>
              {previewing ? 'Generating…' : mode === 'stereo' ? 'Preview Stereo' : 'Preview BMP'}
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSend}
              disabled={sending || !status.connected}
              title={!status.connected ? 'Connect to glasses first' : ''}
            >
              {sending ? 'Sending…' : mode === 'stereo' ? 'Send Stereo' : 'Send to Glasses'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={handleClear}>Clear</button>
          </div>
        </>
      )}

      {!status.connected && (
        <div style={{ marginTop: 14, color: 'var(--muted)', fontSize: 12 }}>
          Connect to glasses on the Home tab before sending.
        </div>
      )}
    </div>
  )
}

function PreviewBox({ src, label, placeholder }) {
  return (
    <div className="preview-box">
      {src
        ? <img src={src} alt={label} />
        : <div className="preview-placeholder">{placeholder}</div>
      }
      <div className="preview-label">{label}</div>
    </div>
  )
}

function ParamSlider({ label, value, min, max, step, onChange, hint }) {
  return (
    <div className="param-row">
      <span className="param-label">{label}</span>
      <input
        type="range"
        className="param-slider"
        min={min} max={max} step={step}
        value={value}
        onChange={e => onChange(step < 1 ? parseFloat(e.target.value) : parseInt(e.target.value, 10))}
      />
      <span className="param-value">{value}</span>
      {hint && <span className="param-hint">{hint}</span>}
    </div>
  )
}

function IconImage() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ margin: '0 auto', display: 'block', opacity: 0.5 }}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}
