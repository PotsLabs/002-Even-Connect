#!/usr/bin/env bash
# KiroshiOS — production build
# Usage: ./build.sh
# Outputs: frontend/src-tauri/target/release/bundle/macos/KiroshiOS.app
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

echo "==> KiroshiOS production build"

# ── 1. Rust / Cargo ───────────────────────────────────────────────────────────
[ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"

# ── 2. Python venv ───────────────────────────────────────────────────────────
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

# ── 3. Python dependencies ────────────────────────────────────────────────────
echo "--> Installing Python dependencies..."
"$PIP" install --quiet -r "$ROOT/requirements.txt"
"$PIP" install --quiet pyinstaller

# ── 4. Build backend sidecar with PyInstaller ─────────────────────────────────
echo "--> Building Python backend sidecar (this takes ~5 min first run)..."
cd "$ROOT"
"$ROOT/.venv/bin/pyinstaller" \
  api.spec \
  --distpath "$ROOT/.build/dist_backend" \
  --workpath "$ROOT/.build/work_backend" \
  --noconfirm

# ── 5. Copy sidecar to Tauri binaries dir ────────────────────────────────────
ARCH="$(uname -m)"
case "$ARCH" in
  arm64)   TARGET="aarch64-apple-darwin" ;;
  x86_64)  TARGET="x86_64-apple-darwin"  ;;
  *)       echo "Unsupported arch: $ARCH"; exit 1 ;;
esac

BINARIES_DIR="$ROOT/frontend/src-tauri/binaries"
mkdir -p "$BINARIES_DIR"

SRC="$ROOT/.build/dist_backend/api"
DEST="$BINARIES_DIR/api-$TARGET"

cp "$SRC" "$DEST"
chmod +x "$DEST"
echo "--> Sidecar: binaries/api-$TARGET ($(du -sh "$DEST" | cut -f1))"

# ── 6. Build Tauri app ────────────────────────────────────────────────────────
echo "--> Building Tauri app..."
cd "$ROOT/frontend"
npm install --silent
npm run tauri build

APP="$ROOT/frontend/src-tauri/target/release/bundle/macos/KiroshiOS.app"
echo ""
echo "==> Build complete!"
echo "    App: $APP"
echo "    Drag KiroshiOS.app to /Applications to install."
echo "    Then open it once — macOS will ask for Bluetooth permission."
echo "    Use the tray icon > 'Launch at Login' to enable auto-start."
