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
elif [ -x "$ROOT/venv/bin/python3" ]; then
  PYTHON="$ROOT/venv/bin/python3"
else
  echo "No venv found — creating one at $ROOT/.venv"
  python3 -m venv "$ROOT/.venv"
  PYTHON="$ROOT/.venv/bin/python3"
fi

# ── 3. Python dependencies ────────────────────────────────────────────────────
echo "--> Installing Python dependencies..."
"$PYTHON" -m pip install --quiet -r "$ROOT/requirements.txt"
"$PYTHON" -m pip install --quiet pyinstaller

# ── 4. Build backend sidecar with PyInstaller ─────────────────────────────────
echo "--> Building Python backend sidecar (this takes ~5 min first run)..."
cd "$ROOT"
"$PYTHON" -m PyInstaller \
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
# tauri.conf.json sets bundle targets to "all", so a plain `tauri build` also
# produces a .dmg. Building the DMG mounts a scratch volume and registers the
# copy inside it with LaunchServices — a registration that outlives the volume
# and competes with /Applications when resolving `open -a KiroshiOS`.
#
# The DMG is a distribution artifact, not something the test loop needs, so
# default to the .app only. Pass --dmg when you actually want a shippable image.
BUNDLES="app"
for arg in "$@"; do
  case "$arg" in
    --dmg) BUNDLES="app,dmg" ;;
    *) echo "Unknown option: $arg"; exit 2 ;;
  esac
done

echo "--> Building Tauri app (bundles: $BUNDLES)..."
cd "$ROOT/frontend"
npm install --silent
npm run tauri build -- --bundles "$BUNDLES"

APP="$ROOT/frontend/src-tauri/target/release/bundle/macos/KiroshiOS.app"
echo ""
echo "==> Build complete!"
echo "    App: $APP"
if [ "$BUNDLES" = "app" ]; then
  echo "    Install with ./install.sh (no DMG built — pass --dmg if you need one)."
else
  echo "    DMG: $ROOT/frontend/src-tauri/target/release/bundle/dmg/"
fi
echo "    Bluetooth permission is granted per bundle id and survives reinstall."
