import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

const DEFAULT_STEREO = { maxDisparity: 6, blurRadius: 3, invertDepth: false }

export default function ImageTab({ status, addToast, addLog }) {
  const [original, setOriginal]       = useState(null)
  const [mode, setMode]               = useState('standard')
  const [bmpPreview, setBmpPreview]   = useState(null)
  const [stereo, setStereo]           = useState(DEFAULT_STEREO)
  const [drag, setDrag]               = useState(false)
  const [previewing, setPreviewing]   = useState(false)
  const [sending, setSending]         = useState(false)

  const [queue, setQueue]             = useState([])
  const [queueIndex, setQueueIndex]   = useState(-1)
  const [dragOverIdx, setDragOverIdx] = useState(null)
  const dragSrcRef                    = useRef(null)

  // Update a single queue item by its ID without replacing the array reference
  const updateQueueItem = (id, updates) =>
    setQueue(q => q.map(item => item.id === id ? { ...item, ...updates } : item))

  const [playing, setPlaying]         = useState(false)
  const [autoInterval, setAutoInterval] = useState(1000)
  const [lastSendMs, setLastSendMs]   = useState(null)

  // Refs so the auto-play loop always sees current values without restarting
  const queueRef        = useRef(queue)
  const queueIndexRef   = useRef(queueIndex)
  const statusRef       = useRef(status)
  const intervalRef     = useRef(autoInterval)
  const playingRef      = useRef(false)

  useEffect(() => { queueRef.current = queue },         [queue])
  useEffect(() => { queueIndexRef.current = queueIndex }, [queueIndex])
  useEffect(() => { statusRef.current = status },       [status])
  useEffect(() => { intervalRef.current = autoInterval }, [autoInterval])

  const fileRef = useRef(null)

  // ── File loading ─────────────────────────────────────────────────────────

  const loadFile = useCallback((file) => {
    if (!file || !file.type.startsWith('image/')) {
      addToast('Please select an image file', 'error')
      return
    }
    const reader = new FileReader()
    reader.onload = (e) => { setOriginal(e.target.result); setBmpPreview(null) }
    reader.readAsDataURL(file)
  }, [addToast])

  const makeQueueItem = (original, itemMode = 'standard', itemStereo = DEFAULT_STEREO) => ({
    id: crypto.randomUUID(),
    original,
    mode: itemMode,
    stereo: itemStereo,
    precomputed: 'pending',
  })

  const triggerPrecompute = useCallback((items) => {
    const payload = items.map(item => ({
      id: item.id,
      imageData: item.original.split(',')[1],
      mode: item.mode,
      ...item.stereo,
    }))
    addLog(`INFO:precompute:Queuing ${items.length} image(s) for precomputation…`)
    api.precompute(payload)
      .then(({ precomputed, errors }) => {
        precomputed.forEach(id => {
          setQueue(q => q.map(qi => qi.id === id ? { ...qi, precomputed: 'ready' } : qi))
        })
        if (precomputed.length) addLog(`INFO:precompute:${precomputed.length} image(s) precomputed and cached`)
        errors.forEach(({ id, error }) => {
          setQueue(q => q.map(qi => qi.id === id ? { ...qi, precomputed: 'error' } : qi))
          addLog(`ERROR:precompute:${error}`)
        })
      })
      .catch((err) => {
        items.forEach(({ id }) =>
          setQueue(q => q.map(qi => qi.id === id ? { ...qi, precomputed: 'error' } : qi))
        )
        addLog(`ERROR:precompute:${err.message}`)
      })
  }, [addLog])

  // Multi-file: maintain insertion order via pre-allocated slots
  const loadFiles = useCallback((files) => {
    const imageFiles = [...files].filter(f => f.type.startsWith('image/'))
    if (imageFiles.length === 0) { addToast('No image files found', 'error'); return }
    if (imageFiles.length === 1) { loadFile(imageFiles[0]); return }

    const results = new Array(imageFiles.length).fill(null)
    let remaining = imageFiles.length

    imageFiles.forEach((file, i) => {
      const reader = new FileReader()
      reader.onload = (e) => {
        results[i] = makeQueueItem(e.target.result)
        remaining--
        if (remaining === 0) {
          const items = results.filter(Boolean)
          setQueue(q => {
            const startIdx = q.length
            if (startIdx === 0) {
              setOriginal(items[0].original)
              setMode('standard')
              setStereo(DEFAULT_STEREO)
              setBmpPreview(null)
              setQueueIndex(0)
            } else {
              setQueueIndex(startIdx)
            }
            return [...q, ...items]
          })
          triggerPrecompute(items)
          addToast(`${items.length} images queued — precomputing…`, 'info')
        }
      }
      reader.readAsDataURL(file)
    })
  }, [addToast, loadFile, triggerPrecompute])

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
    const { files } = e.dataTransfer
    if (files.length > 1) loadFiles(files)
    else if (files.length === 1) loadFile(files[0])
  }

  // ── Send helpers ─────────────────────────────────────────────────────────

  const b64 = (dataUrl) => dataUrl.split(',')[1]

  const sendItem = async (dataUrl, itemMode, itemStereo) => {
    setSending(true)
    const start = performance.now()
    try {
      if (itemMode === 'stereo') {
        await api.sendStereoImage(b64(dataUrl), itemStereo)
      } else {
        await api.sendImage(b64(dataUrl))
      }
      return performance.now() - start
    } finally {
      setSending(false)
    }
  }

  const handleSend = async () => {
    if (!original) return
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    try {
      const ms = await sendItem(original, mode, stereo)
      addToast(`${mode === 'stereo' ? 'Stereo image' : 'Image'} sent (${Math.round(ms)}ms)`, 'success')
    } catch (e) {
      addToast(e.message, 'error')
    }
  }

  const handlePreview = async () => {
    if (!original) return
    setPreviewing(true); setBmpPreview(null)
    try {
      if (mode === 'stereo') {
        setBmpPreview(await api.previewStereoBmp(b64(original), stereo))
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

  const handleClear = () => {
    setOriginal(null); setBmpPreview(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const setStereoParam = (key, val) => {
    setStereo(s => ({ ...s, [key]: val }))
    setBmpPreview(null)
  }

  const switchMode = (m) => { setMode(m); setBmpPreview(null) }

  // ── Queue management ─────────────────────────────────────────────────────

  const addToQueue = () => {
    if (!original) return
    const item = makeQueueItem(original, mode, stereo)
    const newIndex = queue.length
    setQueue(q => [...q, item])
    setQueueIndex(newIndex)
    triggerPrecompute([item])
    addToast('Added to queue — precomputing…', 'info')
  }

  const removeFromQueue = (idx) => {
    const removing = queue[idx]
    if (removing?.precomputed !== 'pending') api.deletePrecomputed(removing.id).catch(() => {})
    const next = queue.filter((_, i) => i !== idx)
    setQueue(next)
    if (next.length === 0) {
      setQueueIndex(-1)
      setPlaying(false)
    } else if (idx < queueIndex) {
      setQueueIndex(queueIndex - 1)
    } else if (idx === queueIndex) {
      setQueueIndex(Math.min(queueIndex, next.length - 1))
    }
  }

  const sendQueueItem = async (item) => {
    setSending(true)
    const start = performance.now()
    const path = item.precomputed === 'ready' ? 'cached' : item.mode === 'stereo' ? 'stereo' : 'standard'
    addLog(`INFO:send:Sending image [${path}]…`)
    try {
      if (item.precomputed === 'ready') {
        await api.sendPrecomputed(item.id)
      } else if (item.mode === 'stereo') {
        await api.sendStereoImage(item.original.split(',')[1], item.stereo)
      } else {
        await api.sendImage(item.original.split(',')[1])
      }
      const ms = Math.round(performance.now() - start)
      addLog(`INFO:send:Done — ${ms}ms via ${path}`)
      return ms
    } catch (err) {
      addLog(`ERROR:send:${err.message}`)
      throw err
    } finally {
      setSending(false)
    }
  }

  const goToQueue = async (idx, silent = false) => {
    const q = queueRef.current
    if (idx < 0 || idx >= q.length) return
    const item = q[idx]
    setQueueIndex(idx)
    setOriginal(item.original)
    setMode(item.mode)
    setStereo(item.stereo)
    setBmpPreview(null)
    if (statusRef.current.connected) {
      try {
        const ms = await sendQueueItem(item)
        setLastSendMs(ms)
        const cached = item.precomputed === 'ready' ? ' (cached)' : ''
        if (!silent) addToast(`Image sent in ${ms}ms${cached}`, 'success')
      } catch (e) {
        if (!silent) addToast(e.message, 'error')
      }
    }
  }

  // ── Drag-to-reorder ───────────────────────────────────────────────────────

  const handleDragStart = (e, i) => {
    dragSrcRef.current = i
    e.dataTransfer.effectAllowed = 'move'
    // Needed for Firefox
    e.dataTransfer.setData('text/plain', i)
  }
  const handleDragEnter = (i) => {
    if (dragSrcRef.current !== null && dragSrcRef.current !== i) setDragOverIdx(i)
  }
  const handleDragOver = (e) => e.preventDefault()
  const handleDragEnd  = () => { setDragOverIdx(null); dragSrcRef.current = null }

  const handleThumbDrop = (e, toIdx) => {
    e.preventDefault()
    const fromIdx = dragSrcRef.current
    if (fromIdx === null || fromIdx === toIdx) { setDragOverIdx(null); return }

    const next = [...queue]
    const [moved] = next.splice(fromIdx, 1)
    next.splice(toIdx, 0, moved)

    let newQueueIdx = queueIndex
    if (queueIndex === fromIdx) {
      newQueueIdx = toIdx
    } else if (fromIdx < queueIndex && toIdx >= queueIndex) {
      newQueueIdx = queueIndex - 1
    } else if (fromIdx > queueIndex && toIdx <= queueIndex) {
      newQueueIdx = queueIndex + 1
    }

    setQueue(next)
    setQueueIndex(newQueueIdx)
    setDragOverIdx(null)
    dragSrcRef.current = null
  }

  // ── Auto-play loop ────────────────────────────────────────────────────────

  useEffect(() => {
    if (!playing || queue.length <= 1) {
      playingRef.current = false
      return
    }
    playingRef.current = true
    let active = true
    let timer = null

    const tick = async () => {
      if (!active || !playingRef.current) return
      const q = queueRef.current
      if (q.length <= 1) { setPlaying(false); return }

      const nextIdx = (queueIndexRef.current + 1) % q.length
      const item = q[nextIdx]

      setQueueIndex(nextIdx)
      setOriginal(item.original)
      setMode(item.mode)
      setStereo(item.stereo)
      setBmpPreview(null)

      const start = performance.now()
      if (statusRef.current.connected) {
        try {
          await sendQueueItem(item)
        } catch (_) {
          // silent during playback
        }
      }

      if (!active) return
      const elapsed = Math.round(performance.now() - start)
      setLastSendMs(elapsed)

      const delay = Math.max(0, intervalRef.current - elapsed)
      timer = setTimeout(tick, delay)
    }

    timer = setTimeout(tick, intervalRef.current)
    return () => {
      active = false
      playingRef.current = false
      clearTimeout(timer)
    }
  }, [playing, queue.length])

  // Stop playback if queue shrinks to 1 or 0
  useEffect(() => {
    if (queue.length <= 1 && playing) setPlaying(false)
  }, [queue.length, playing])

  // ── Render ────────────────────────────────────────────────────────────────

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
          <p>Drop images here, click to browse, or paste with Ctrl+V</p>
          <p style={{ fontSize: '11px', marginTop: 4 }}>
            PNG, JPG, BMP — resized to 576×136 monochrome. Drop multiple to auto-queue.
          </p>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: 'none' }}
            onChange={(e) => loadFiles(e.target.files)}
          />
        </div>
      ) : (
        <>
          {/* Mode toggle */}
          <div className="mode-toggle">
            <button className={`mode-btn ${mode === 'standard' ? 'active' : ''}`} onClick={() => switchMode('standard')}>
              Standard
            </button>
            <button className={`mode-btn ${mode === 'stereo' ? 'active' : ''}`} onClick={() => switchMode('stereo')}>
              Stereo 3D
            </button>
          </div>

          {mode === 'stereo' && (
            <div className="stereo-params">
              <div className="stereo-params-title">Depth Parameters</div>
              <ParamSlider label="Max Disparity" value={stereo.maxDisparity} min={1} max={20} step={1}
                onChange={v => setStereoParam('maxDisparity', v)} hint="px — how far foreground floats" />
              <ParamSlider label="Blur Radius" value={stereo.blurRadius} min={0} max={10} step={0.5}
                onChange={v => setStereoParam('blurRadius', v)} hint="depth map smoothing, higher = less fringing" />
              <div className="param-row">
                <span className="param-label">Invert Depth</span>
                <label className="toggle-switch">
                  <input type="checkbox" checked={stereo.invertDepth}
                    onChange={e => setStereoParam('invertDepth', e.target.checked)} />
                  <span className="toggle-track" />
                </label>
                <span className="param-hint">dark = near (for point clouds / light backgrounds)</span>
              </div>
            </div>
          )}

          {mode === 'standard' ? (
            <div className="image-preview-row" style={{ marginTop: 16 }}>
              <PreviewBox src={original} label="Original" />
              <PreviewBox
                src={typeof bmpPreview === 'string' ? bmpPreview : null}
                label="Glasses view (576×136 mono)" placeholder="Click Preview BMP"
              />
            </div>
          ) : (
            <>
              <div className="image-preview-row" style={{ gridTemplateColumns: '1fr', marginTop: 16 }}>
                <PreviewBox src={original} label="Original" />
              </div>
              <div className="image-preview-row stereo-pair" style={{ marginTop: 8 }}>
                <PreviewBox src={bmpPreview?.left ?? null} label="Left eye" placeholder="Click Preview to generate" />
                <PreviewBox src={bmpPreview?.right ?? null} label="Right eye" placeholder="Click Preview to generate" />
              </div>
            </>
          )}

          <div className="btn-row" style={{ marginTop: 14 }}>
            <button className="btn btn-ghost btn-sm" onClick={handlePreview} disabled={previewing}>
              {previewing ? 'Generating…' : mode === 'stereo' ? 'Preview Stereo' : 'Preview BMP'}
            </button>
            <button className="btn btn-primary" onClick={handleSend}
              disabled={sending || !status.connected}
              title={!status.connected ? 'Connect to glasses first' : ''}>
              {sending ? 'Sending…' : mode === 'stereo' ? 'Send Stereo' : 'Send to Glasses'}
            </button>
            <button className="btn btn-ghost btn-sm" onClick={addToQueue}>+ Queue</button>
            <button className="btn btn-ghost btn-sm" onClick={handleClear}>Clear</button>
          </div>

          {queue.length > 0 && (
            <div className="queue-section">
              <div className="queue-header">
                <span className="queue-label">
                  Queue — {queue.length} image{queue.length !== 1 ? 's' : ''}
                </span>
                <div className="queue-nav">
                  <button className="btn btn-ghost btn-sm queue-nav-btn"
                    onClick={() => goToQueue(queueIndex - 1)}
                    disabled={queueIndex <= 0 || sending}>←</button>
                  <span className="queue-counter">{queueIndex + 1} / {queue.length}</span>
                  <button className="btn btn-ghost btn-sm queue-nav-btn"
                    onClick={() => goToQueue(queueIndex + 1)}
                    disabled={queueIndex >= queue.length - 1 || sending}>→</button>
                </div>
              </div>

              <div className="queue-strip">
                {queue.map((item, i) => (
                  <div
                    key={i}
                    className={`queue-thumb ${i === queueIndex ? 'active' : ''} ${dragOverIdx === i ? 'drag-over' : ''}`}
                    draggable
                    onClick={() => goToQueue(i)}
                    onDragStart={e => handleDragStart(e, i)}
                    onDragEnter={() => handleDragEnter(i)}
                    onDragOver={handleDragOver}
                    onDrop={e => handleThumbDrop(e, i)}
                    onDragEnd={handleDragEnd}
                    title={`Image ${i + 1}${item.mode === 'stereo' ? ' (Stereo)' : ''} — drag to reorder`}
                  >
                    <img src={item.original} alt={`Queue ${i + 1}`} draggable={false} />
                    {item.mode === 'stereo' && <div className="queue-thumb-badge">3D</div>}
                    <div className={`queue-thumb-cache queue-thumb-cache--${item.precomputed}`}
                      title={item.precomputed === 'ready' ? 'Precomputed' : item.precomputed === 'error' ? 'Precompute failed' : 'Computing…'} />
                    <button className="queue-thumb-remove"
                      onClick={e => { e.stopPropagation(); removeFromQueue(i) }}
                      title="Remove">×</button>
                  </div>
                ))}
              </div>

              {queue.length > 1 && (
                <div className="queue-controls">
                  <button
                    className={`btn btn-sm ${playing ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setPlaying(p => !p)}
                    disabled={!status.connected}
                    title={!status.connected ? 'Connect glasses to use playback' : ''}
                  >
                    {playing ? '⏸ Pause' : '▶ Play'}
                  </button>

                  <div className="queue-speed">
                    <span className="queue-speed-label">Interval</span>
                    <input
                      type="range"
                      className="param-slider"
                      min={200} max={5000} step={100}
                      value={autoInterval}
                      onChange={e => setAutoInterval(parseInt(e.target.value, 10))}
                    />
                    <span className="queue-speed-val">{autoInterval}ms</span>
                  </div>

                  {lastSendMs !== null && (
                    <div className="queue-fps-row">
                      <span className="queue-fps-stat">last send: {lastSendMs}ms</span>
                      <span className="queue-fps-stat">
                        ~{lastSendMs > 0 ? (1000 / Math.max(lastSendMs, autoInterval)).toFixed(1) : '—'} fps
                      </span>
                    </div>
                  )}
                </div>
              )}

              {!status.connected && (
                <div style={{ marginTop: 10, color: 'var(--muted)', fontSize: 11 }}>
                  Connect glasses to send on navigation.
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!status.connected && !original && (
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
      {src ? <img src={src} alt={label} /> : <div className="preview-placeholder">{placeholder}</div>}
      <div className="preview-label">{label}</div>
    </div>
  )
}

function ParamSlider({ label, value, min, max, step, onChange, hint }) {
  return (
    <div className="param-row">
      <span className="param-label">{label}</span>
      <input type="range" className="param-slider" min={min} max={max} step={step} value={value}
        onChange={e => onChange(step < 1 ? parseFloat(e.target.value) : parseInt(e.target.value, 10))} />
      <span className="param-value">{value}</span>
      {hint && <span className="param-hint">{hint}</span>}
    </div>
  )
}

function IconImage() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round"
      style={{ margin: '0 auto', display: 'block', opacity: 0.5 }}>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21 15 16 10 5 21" />
    </svg>
  )
}
