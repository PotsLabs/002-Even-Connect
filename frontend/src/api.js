const BASE = '/api'

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
  status:       ()       => request('/status',       {},                                                             FAST),
  connect:      ()       => request('/connect',      { method: 'POST' }),
  disconnect:   ()       => request('/disconnect',   { method: 'POST' }),
  sendText:     (text)   => request('/send-text',    { method: 'POST', body: JSON.stringify({ text }) },            SEND),

  sendImage:        (b64)          => request('/send-image',        { method: 'POST', body: JSON.stringify({ imageData: b64 }) },                   SEND),
  previewBmp:       (b64)          => request('/preview-bmp',       { method: 'POST', body: JSON.stringify({ imageData: b64 }) }),
  sendStereoImage:  (b64, params)  => request('/send-stereo-image', { method: 'POST', body: JSON.stringify({ imageData: b64, ...params }) },        STEREO),
  previewStereoBmp: (b64, params)  => request('/preview-stereo-bmp',{ method: 'POST', body: JSON.stringify({ imageData: b64, ...params }) }),

  // Precomputed frame cache
  precompute:       (images)  => request('/queue/precompute',          { method: 'POST', body: JSON.stringify({ images }) },     STEREO),
  sendPrecomputed:  (id)      => request(`/send-precomputed/${id}`,    { method: 'POST' },                                       SEND),
  deletePrecomputed:(id)      => request(`/queue/precomputed/${id}`,   { method: 'DELETE' }),

  // Compose (background + image layers + text layers)
  previewCompose:       (backgroundData, blocks, imageLayers = [])                          => request('/preview-compose',        { method: 'POST', body: JSON.stringify({ backgroundData, blocks, imageLayers }) }),
  sendCompose:          (backgroundData, blocks, imageLayers = [])                          => request('/send-compose',           { method: 'POST', body: JSON.stringify({ backgroundData, blocks, imageLayers }) },          SEND),
  precomputeCompose:    (backgroundData, blocks, imageLayers = [])                          => request('/precompute-compose',     { method: 'POST', body: JSON.stringify({ backgroundData, blocks, imageLayers }) },          STEREO),
  previewStereoCompose: (backgroundData, backgroundZ = 0, blocks, imageLayers = [], maxDisparity = 10) => request('/preview-stereo-compose', { method: 'POST', body: JSON.stringify({ backgroundData, backgroundZ, blocks, imageLayers, maxDisparity }) }),
  sendStereoCompose:    (backgroundData, backgroundZ = 0, blocks, imageLayers = [], maxDisparity = 10) => request('/send-stereo-compose',    { method: 'POST', body: JSON.stringify({ backgroundData, backgroundZ, blocks, imageLayers, maxDisparity }) }, STEREO),

  // Obsidian Local REST API proxy
  obsidian: {
    getConfig:    ()                     => request('/obsidian/config'),
    setConfig:    (url, api_key)         => request('/obsidian/config',           { method: 'POST', body: JSON.stringify({ url, api_key }) }),
    ping:         ()                     => request('/obsidian/ping'),
    listFiles:    ()                     => request('/obsidian/files'),
    getFile:      (path)                 => request(`/obsidian/file/${path}`),
    writeFile:    (path, content)        => request(`/obsidian/file/${path}`,     { method: 'PUT',    body: JSON.stringify({ content }) }),
    appendFile:   (path, content)        => request(`/obsidian/file/${path}/append`, { method: 'POST', body: JSON.stringify({ content }) }),
    deleteFile:   (path)                 => request(`/obsidian/file/${path}`,     { method: 'DELETE' }),
    search:       (query)                => request('/obsidian/search',           { method: 'POST', body: JSON.stringify({ query }) }),
  },
}
