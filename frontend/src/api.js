// In Tauri builds the webview's base URL is tauri://localhost, so relative /api
// paths never reach the Python backend on port 8000.  Use the full URL instead.
// In a plain browser (Vite dev proxy or direct access) the relative path is fine.
export const BASE = (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window)
  ? 'http://localhost:8000/api'
  : '/api'

// For callers that can't go through request(): SSE streams, EventSource, and
// multipart uploads all need the raw URL but the same base resolution.
export const apiUrl = (path) => BASE + path

async function request(path, options = {}, timeoutMs = 30_000) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(BASE + path, {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
    return data
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Request timed out')
    throw e
  } finally {
    clearTimeout(timer)
  }
}

const FAST = 5_000   // status / config polls
const SEND = 30_000  // single BLE image send
const STEREO = 60_000 // stereo = two full images over BLE

export const api = {
  // Core endpoints (api_v3.py)
  status:            ()                                                                    => request('/status',               {},                                                           FAST),
  connectStream:     ()                                                                    => request('/connect-stream',       { method: 'POST' }),
  disconnect:        ()                                                                    => request('/disconnect',           { method: 'POST' }),
  syncTime:          ()                                                                    => request('/sync-time',            { method: 'POST' },                                           FAST),
  eventsStream:      ()                                                                    => request('/events/stream',        {}),

  // Send endpoints
  sendText:          (text)                                                                => request('/send-text',            { method: 'POST', body: JSON.stringify({ text }) },                      SEND),
  previewCompose:    (payload)                                                             => request('/preview-compose',      { method: 'POST', body: JSON.stringify(payload) },                        SEND),
  sendCompose:       (payload)                                                             => request('/send-compose',         { method: 'POST', body: JSON.stringify(payload) },                        STEREO),
  sendStereoPair:    (layers, maxDisparity = 10)                                           => request('/send-stereo-compose',  { method: 'POST', body: JSON.stringify({ layers, maxDisparity }) },       STEREO),

  // Layout endpoints
  listLayouts:       ()                                                                    => request('/layouts',              {},                                                           FAST),
  saveLayout:        (name, layers)                                                        => request('/layouts',              { method: 'POST', body: JSON.stringify({ name, layers }) },               FAST),
  getLayout:         (layoutId)                                                            => request(`/layouts/${layoutId}`,  {},                                                           FAST),
  deleteLayout:      (layoutId)                                                            => request(`/layouts/${layoutId}`,  { method: 'DELETE' },                                         FAST),

  // 3D model endpoints
  listModels:        ()                                                                    => request('/models',               {},                                                           FAST),
  preview3DModel:    (modelId, payload)                                                    => request(`/models/${modelId}/preview`, { method: 'POST', body: JSON.stringify(payload) },         SEND),
  send3DModel:       (modelId, payload)                                                    => request(`/models/${modelId}/send`,    { method: 'POST', body: JSON.stringify(payload) },         STEREO),

  // ────── DEFERRED (M0.5 → Preview endpoints) ──────────────────────────────
  // previewBmp: show 1-bit BMP preview before send
  // previewStereoPair: show left/right stereo pair before send
  // See: KIROSHI_OS_SPEC.md § "Deferred / Nice-to-Have"

  // ────── REMOVED (v2 → v3 rewrite) ─────────────────────────────────────────
  // Frame cache optimization: precompute, sendPrecomputed, deletePrecomputed
  // Text composition: previewCompose, sendCompose, precomputeCompose
  // Obsidian proxy: obsidian.* endpoints (use integrations/obsidian.py instead)
  // See: KIROSHI_OS_SPEC.md § "M0 — Known Issues"
}
