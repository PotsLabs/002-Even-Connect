#!/usr/bin/env bash
# KiroshiOS — single-entry launcher
# Works from any shell (bash/zsh) and any working directory.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── 1. Rust / Cargo ───────────────────────────────────────────────────────────
if [ -f "$HOME/.cargo/env" ]; then
  source "$HOME/.cargo/env"
fi

# ── 2. Python venv — prefer .venv, fall back to venv ─────────────────────────
if [ -x "$ROOT/.venv/bin/python3" ]; then
  PYTHON="$ROOT/.venv/bin/python3"
  PIP="$ROOT/.venv/bin/pip"
elif [ -x "$ROOT/venv/bin/python3" ]; then
  PYTHON="$ROOT/venv/bin/python3"
  PIP="$ROOT/venv/bin/pip"
else
  echo "No venv found — creating one at $ROOT/.venv"
  python3 -m venv "$ROOT/.venv"
  PYTHON="$ROOT/.venv/bin/python3"
  PIP="$ROOT/.venv/bin/pip"
fi

# ── 3. Install / sync Python dependencies ────────────────────────────────────
echo "Syncing Python dependencies..."
"$PIP" install --quiet -r "$ROOT/requirements.txt"

# ── 4. Start the Python backend in the background ────────────────────────────
UVICORN="$(dirname "$PYTHON")/uvicorn"
echo "Starting Python backend..."
"$UVICORN" api:app --host 127.0.0.1 --port 8000 \
  --app-dir "$ROOT" --log-level warning &
BACKEND_PID=$!

# Kill the backend when this script exits (Ctrl-C or Tauri window closes)
trap 'echo "Stopping backend (pid $BACKEND_PID)..."; kill "$BACKEND_PID" 2>/dev/null; wait "$BACKEND_PID" 2>/dev/null' EXIT

# ── 5. Wait until the backend is accepting connections (max 15 s) ─────────────
echo "Waiting for backend..."
for i in $(seq 1 30); do
  if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/status')" 2>/dev/null; then
    echo "Backend ready."
    break
  fi
  sleep 0.5
  if [ "$i" -eq 30 ]; then
    echo "Backend did not start in time — check api.py for errors."
    exit 1
  fi
done

# ── 6. Install frontend dependencies and launch Tauri ─────────────────────────
echo "Installing frontend dependencies..."
cd "$ROOT/frontend"
npm install --silent

echo "Launching KiroshiOS..."
npm run tauri:dev
