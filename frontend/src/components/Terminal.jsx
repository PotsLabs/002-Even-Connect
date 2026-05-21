import { useEffect, useRef } from 'react'

const LEVEL_COLOR = {
  INFO:     '#4ade80',
  WARNING:  '#fbbf24',
  WARN:     '#fbbf24',
  ERROR:    '#f87171',
  CRITICAL: '#f87171',
  DEBUG:    '#94a3b8',
}

// Split "LEVEL:logger.name:rest of message (may contain colons)"
function parseLine(raw) {
  const first = raw.indexOf(':')
  if (first === -1) return { level: null, logger: null, message: raw }
  const second = raw.indexOf(':', first + 1)
  if (second === -1) return { level: raw.slice(0, first), logger: null, message: raw.slice(first + 1) }
  return {
    level:   raw.slice(0, first),
    logger:  raw.slice(first + 1, second),
    message: raw.slice(second + 1),
  }
}

export default function Terminal({ lines, active }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines, active])

  return (
    <div className="terminal">
      <div className="terminal-bar">
        <span className="terminal-traffic" style={{ background: '#ef4444' }} />
        <span className="terminal-traffic" style={{ background: '#f59e0b' }} />
        <span className="terminal-traffic" style={{ background: '#22c55e' }} />
        <span className="terminal-title">EvenConnect — BLE Scanner</span>
        {active && <span className="terminal-badge">scanning</span>}
      </div>
      <div className="terminal-body">
        {lines.length === 0 && !active && (
          <span className="term-placeholder">
            Terminal output will appear here during scan…
          </span>
        )}
        {lines.map((raw, i) => {
          const { level, logger, message } = parseLine(raw)
          const levelColor = (level && LEVEL_COLOR[level]) || '#d1d5db'
          return (
            <div key={i} className="term-line">
              {level && (
                <>
                  <span className="term-level" style={{ color: levelColor }}>{level}</span>
                  <span className="term-sep">:</span>
                </>
              )}
              {logger && (
                <>
                  <span className="term-logger">{logger}</span>
                  <span className="term-sep">:</span>
                </>
              )}
              <span className="term-msg">{message}</span>
            </div>
          )
        })}
        {active && (
          <div className="term-line">
            <span className="term-cursor">█</span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
