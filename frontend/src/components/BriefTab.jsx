import { useEffect, useState } from 'react'
import { api } from '../api'

const STORAGE_KEY = 'kiroshi_brief_inputs'

const DOMAINS = [
  { value: 'vision',   label: 'Vision Company — HUD XR' },
  { value: 'masters',  label: 'Masters Coursework' },
  { value: 'fornix',   label: 'Fornix — Clinical DB' },
  { value: 'identity', label: 'Identity Engineering' },
  { value: 'physical', label: 'Physical Infrastructure' },
  { value: 'other',    label: 'Other' },
]

const CHECKS = [
  { key: 'sleep',     label: 'Adequate sleep' },
  { key: 'gym',       label: 'Gym / movement done' },
  { key: 'bible',     label: 'Bible reading done' },
  { key: 'no_stim',   label: 'No stimulant first 30 min' },
  { key: 'no_scroll', label: 'No scroll before work' },
]

const SCREENS = [
  { id: 'brief',  label: 'Operation Brief' },
  { id: 'blocks', label: 'Scheduled Blocks' },
  { id: 'power',  label: 'Power Index' },
]

const MAX_BLOCKS = 4

const DEFAULTS = {
  energy: 7,
  focus: 7,
  tStart: '06:00',
  tEnd: '21:00',
  weekPriority: '',
  oneThing: '',
  domain: 'vision',
  stopCriteria: '',
  checks: {},
  blocks: [],
  screens: ['brief', 'blocks', 'power'],
  dwellSeconds: 6,
}

function loadSaved() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS
  } catch {
    return DEFAULTS
  }
}

// Ported from morning-card.html so the tab shows the same numbers the
// glasses will render.
function minutesBetween(a, b) {
  if (!a || !b) return 0
  const [ah, am] = a.split(':').map(Number)
  const [bh, bm] = b.split(':').map(Number)
  return Math.max(0, (bh * 60 + bm) - (ah * 60 + am))
}

function fmtMin(m) {
  const h = Math.floor(m / 60), mm = m % 60
  if (h === 0) return `${mm}min`
  return mm === 0 ? `${h}h` : `${h}h ${mm}min`
}

function calcTier(energy, focus, totalMin) {
  const score = (energy + focus) / 2
  if (score >= 7 && totalMin >= 90) return 'DEEP WORK'
  if (score >= 5 && totalMin >= 45) return 'STRUCTURED'
  return 'MAINTENANCE'
}

function calcPower(energy, focus, checksDone) {
  return Math.round(((energy + focus) / 20) * 50 + (checksDone / 5) * 30 + 20)
}

export default function BriefTab({ status, addToast }) {
  const [f, setF] = useState(loadSaved)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(f)) } catch { /* private mode */ }
  }, [f])

  const set = (patch) => setF((prev) => ({ ...prev, ...patch }))

  const toggleCheck = (key) =>
    set({ checks: { ...f.checks, [key]: !f.checks[key] } })

  // Rebuild from SCREENS so send order stays canonical regardless of click order.
  const toggleScreen = (id) => {
    const next = new Set(f.screens)
    next.has(id) ? next.delete(id) : next.add(id)
    set({ screens: SCREENS.map((s) => s.id).filter((s) => next.has(s)) })
  }

  const addBlock = () => {
    if (f.blocks.length >= MAX_BLOCKS) return
    set({ blocks: [...f.blocks, { name: '', start: '', end: '' }] })
  }

  const updateBlock = (i, patch) =>
    set({ blocks: f.blocks.map((b, idx) => (idx === i ? { ...b, ...patch } : b)) })

  const removeBlock = (i) =>
    set({ blocks: f.blocks.filter((_, idx) => idx !== i) })

  const windowMin = minutesBetween(f.tStart, f.tEnd)
  const checksDone = CHECKS.filter((c) => f.checks[c.key]).length
  const tier = calcTier(f.energy, f.focus, windowMin)
  const power = calcPower(f.energy, f.focus, checksDone)

  const handleSend = async () => {
    if (!status.connected) { addToast('Glasses not connected', 'error'); return }
    if (f.screens.length === 0) { addToast('Select at least one screen', 'error'); return }
    setSending(true)
    try {
      const res = await api.sendBrief(f)
      addToast(`Brief sent — ${res.tier} · index ${res.power.total}`, 'success')
    } catch (e) {
      addToast(e.message, 'error')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="tab-panel">
      <div className="tab-title">Morning Brief</div>

      {/* live readout of what the glasses will show */}
      <div className="card">
        <div className="card-label">Computed</div>
        <div style={{ display: 'flex', gap: 28, alignItems: 'baseline', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em' }}>TIER</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{tier}</div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em' }}>POWER INDEX</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{power}<span style={{ fontSize: 13, color: 'var(--muted)' }}>/100</span></div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em' }}>WINDOW</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{fmtMin(windowMin)}</div>
          </div>
          <div>
            <div style={{ fontSize: 10, color: 'var(--muted)', letterSpacing: '0.08em' }}>CHECKS</div>
            <div style={{ fontSize: 20, fontWeight: 700 }}>{checksDone}<span style={{ fontSize: 13, color: 'var(--muted)' }}>/5</span></div>
          </div>
        </div>
      </div>

      {/* resource assessment */}
      <div className="card">
        <div className="card-label">Resource Assessment</div>
        {['energy', 'focus'].map((k) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <span className="compose-ctrl-label" style={{ minWidth: 60, textTransform: 'capitalize' }}>{k}</span>
            <input
              type="range" className="param-slider" min={1} max={10} step={1}
              value={f[k]}
              onChange={(e) => set({ [k]: parseInt(e.target.value, 10) })}
            />
            <span className="compose-ctrl-val" style={{ minWidth: 24 }}>{f[k]}</span>
          </div>
        ))}

        <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Start</div>
            <input type="time" className="note-heading-input" style={{ width: '100%' }}
              value={f.tStart} onChange={(e) => set({ tStart: e.target.value })} />
          </label>
          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>End</div>
            <input type="time" className="note-heading-input" style={{ width: '100%' }}
              value={f.tEnd} onChange={(e) => set({ tEnd: e.target.value })} />
          </label>
        </div>
      </div>

      {/* priorities */}
      <div className="card">
        <div className="card-label">Priorities</div>
        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>This week&apos;s decade service</div>
        <input className="note-heading-input" style={{ width: '100%', marginBottom: 12 }}
          placeholder="e.g. Vision HUD mobile port"
          value={f.weekPriority} onChange={(e) => set({ weekPriority: e.target.value })} />

        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>The one thing today</div>
        <input className="note-heading-input" style={{ width: '100%', marginBottom: 12 }}
          placeholder="e.g. Finish Fornix schema"
          value={f.oneThing} onChange={(e) => set({ oneThing: e.target.value })} />

        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Domain</div>
        <select className="note-heading-input" style={{ width: '100%', marginBottom: 12 }}
          value={f.domain} onChange={(e) => set({ domain: e.target.value })}>
          {DOMAINS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>

        <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>Stopping criteria</div>
        <input className="note-heading-input" style={{ width: '100%' }}
          placeholder="e.g. 13:00 or schema PR merged"
          value={f.stopCriteria} onChange={(e) => set({ stopCriteria: e.target.value })} />
      </div>

      {/* work blocks */}
      <div className="card">
        <div className="card-label">Work Blocks ({f.blocks.length}/{MAX_BLOCKS})</div>
        {f.blocks.map((b, i) => (
          <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center', marginBottom: 6 }}>
            <span style={{ fontSize: 11, color: 'var(--muted)', minWidth: 20 }}>
              {String(i + 1).padStart(2, '0')}
            </span>
            <input className="note-heading-input" style={{ flex: 1 }} placeholder="Block label"
              value={b.name} onChange={(e) => updateBlock(i, { name: e.target.value })} />
            <input type="time" className="note-heading-input" style={{ width: 110 }}
              value={b.start} onChange={(e) => updateBlock(i, { start: e.target.value })} />
            <input type="time" className="note-heading-input" style={{ width: 110 }}
              value={b.end} onChange={(e) => updateBlock(i, { end: e.target.value })} />
            <span style={{ fontSize: 11, color: 'var(--muted)', minWidth: 56, textAlign: 'right' }}>
              {minutesBetween(b.start, b.end) > 0 ? fmtMin(minutesBetween(b.start, b.end)) : '—'}
            </span>
            <button className="note-delete-btn" onClick={() => removeBlock(i)} title="Remove block">×</button>
          </div>
        ))}
        <button className="btn btn-ghost btn-sm" onClick={addBlock} disabled={f.blocks.length >= MAX_BLOCKS}>
          + Add Block
        </button>
      </div>

      {/* status checks */}
      <div className="card">
        <div className="card-label">Status Checks</div>
        {CHECKS.map((c) => (
          <label key={c.key} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, marginBottom: 6, cursor: 'pointer' }}>
            <input type="checkbox" checked={!!f.checks[c.key]} onChange={() => toggleCheck(c.key)} />
            {c.label}
          </label>
        ))}
      </div>

      {/* send */}
      <div className="card">
        <div className="card-label">Send</div>
        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 12 }}>
          {SCREENS.map((s) => (
            <label key={s.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, cursor: 'pointer' }}>
              <input type="checkbox" checked={f.screens.includes(s.id)} onChange={() => toggleScreen(s.id)} />
              {s.label}
            </label>
          ))}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
          <span className="compose-ctrl-label" style={{ minWidth: 60 }}>Dwell</span>
          <input type="range" className="param-slider" min={2} max={15} step={1}
            value={f.dwellSeconds}
            onChange={(e) => set({ dwellSeconds: parseInt(e.target.value, 10) })} />
          <span className="compose-ctrl-val" style={{ minWidth: 34 }}>{f.dwellSeconds}s</span>
        </div>

        <div className="btn-row">
          <button className="btn btn-primary" onClick={handleSend}
            disabled={sending || !status.connected || f.screens.length === 0}
            title={!status.connected ? 'Connect to glasses first' : ''}>
            {sending ? 'Sending…' : 'Send Brief to Glasses'}
          </button>
        </div>

        {!status.connected && (
          <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 10 }}>
            Connect to glasses on the Home tab before sending.
          </div>
        )}
        <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 10, lineHeight: 1.6 }}>
          Screens are pushed in order and each is held for the dwell time. Sending
          {' '}{f.screens.length} screen{f.screens.length === 1 ? '' : 's'} takes about
          {' '}{Math.max(0, (f.screens.length - 1) * f.dwellSeconds)}s.
        </div>
      </div>
    </div>
  )
}
