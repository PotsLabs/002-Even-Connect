const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`)
  return data
}

export const api = {
  status:       ()       => request('/status'),
  connect:      ()       => request('/connect',      { method: 'POST' }),
  disconnect:   ()       => request('/disconnect',   { method: 'POST' }),
  sendText:     (text)   => request('/send-text',    { method: 'POST', body: JSON.stringify({ text }) }),
  sendImage:       (b64)              => request('/send-image',        { method: 'POST', body: JSON.stringify({ imageData: b64 }) }),
  previewBmp:      (b64)              => request('/preview-bmp',       { method: 'POST', body: JSON.stringify({ imageData: b64 }) }),
  sendStereoImage: (b64, params) => request('/send-stereo-image',  { method: 'POST', body: JSON.stringify({ imageData: b64, ...params }) }),
  previewStereoBmp:(b64, params) => request('/preview-stereo-bmp', { method: 'POST', body: JSON.stringify({ imageData: b64, ...params }) }),
}
