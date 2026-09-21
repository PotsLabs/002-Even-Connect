#!/usr/bin/env bash
# KiroshiOS — uninstall then reinstall the full application.
#
# This is the standard way to test a change: never patch a running app or
# trust that /Applications holds what you just built. Tear the whole thing
# down, put the fresh build in place, and verify what is actually running.
#
# Usage:
#   ./install.sh            build, uninstall, install, verify
#   ./install.sh --no-build use the existing build output
#   ./install.sh --uninstall-only
#
# Bluetooth permission is deliberately NOT reset: the TCC grant is keyed on
# the bundle id, survives reinstall, and resetting it would make macOS
# re-prompt on every test cycle.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
APP_NAME="KiroshiOS.app"
INSTALLED="/Applications/$APP_NAME"
BUILT="$ROOT/frontend/src-tauri/target/release/bundle/macos/$APP_NAME"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

DO_BUILD=1
UNINSTALL_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-build)       DO_BUILD=0 ;;
    --uninstall-only) UNINSTALL_ONLY=1; DO_BUILD=0 ;;
    *) echo "Unknown option: $arg"; exit 2 ;;
  esac
done

# ── 1. Build ──────────────────────────────────────────────────────────────────
if [ "$DO_BUILD" -eq 1 ]; then
  echo "==> Building"
  "$ROOT/build.sh"
fi

# ── 2. Stop everything ────────────────────────────────────────────────────────
# Both the Tauri shell and the PyInstaller sidecar, wherever they were launched
# from. A sidecar routinely outlives its parent and keeps squatting :8000, which
# makes the next launch look like a backend that will not start.
echo "==> Stopping running instances"
pkill -f "$APP_NAME/Contents/MacOS" 2>/dev/null || true
sleep 2
pkill -9 -f "$APP_NAME/Contents/MacOS" 2>/dev/null || true
sleep 1

if lsof -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "    WARNING: something still holds :8000 —"
  lsof -iTCP:8000 -sTCP:LISTEN | tail -n +2 | sed 's/^/      /'
fi

# ── 3. Detach leftover DMG scratch volumes ────────────────────────────────────
# Detach BEFORE unregistering: unregistering a path on a still-mounted volume
# lets LaunchServices re-add it from the live volume moments later.
for vol in /Volumes/dmg.*; do
  [ -d "$vol" ] || continue
  echo "==> Detaching $vol"
  hdiutil detach "$vol" -force >/dev/null 2>&1 || true
done

# ── 4. Unregister every known copy ────────────────────────────────────────────
# Each successful build registers the copy inside the DMG scratch volume. Those
# volumes get ejected but the registration survives, so `open -a KiroshiOS` can
# resolve to a copy that no longer exists or, worse, a stale one that does.
# Pass an argument to keep that one path registered.
prune_registrations() {
  [ -x "$LSREGISTER" ] || return 0
  "$LSREGISTER" -dump 2>/dev/null \
    | grep -oE "/[^ ]*$APP_NAME" \
    | sort -u \
    | while read -r path; do
        [ "$path" = "${1:-}" ] && continue
        echo "    - $path"
        "$LSREGISTER" -u "$path" 2>/dev/null || true
      done
}

echo "==> Unregistering stale LaunchServices entries"
prune_registrations ""

# ── 5. Remove the installed app ───────────────────────────────────────────────
if [ -d "$INSTALLED" ]; then
  echo "==> Removing $INSTALLED"
  rm -rf "$INSTALLED"
else
  echo "==> Nothing installed at $INSTALLED"
fi

if [ "$UNINSTALL_ONLY" -eq 1 ]; then
  echo ""
  echo "==> Uninstalled. Bluetooth permission left intact."
  exit 0
fi

# ── 6. Install ────────────────────────────────────────────────────────────────
if [ ! -d "$BUILT" ]; then
  echo "No build found at $BUILT — run without --no-build." >&2
  exit 1
fi

echo "==> Installing to $INSTALLED"
ditto "$BUILT" "$INSTALLED"

if ! diff -r "$INSTALLED" "$BUILT" >/dev/null 2>&1; then
  echo "Installed bundle does not match the build output." >&2
  exit 1
fi
echo "    bundles identical"

# Register only the installed copy, so `open -a` cannot pick anything else.
if [ -x "$LSREGISTER" ]; then
  "$LSREGISTER" -f "$INSTALLED" 2>/dev/null || true
  # Second pass: LaunchServices re-adds entries during the run — a detached
  # scratch volume can reappear in the database after the first prune — so
  # sweep again now that the install is in place.
  echo "==> Pruning registrations that reappeared during install"
  prune_registrations "$INSTALLED"
fi

# ── 7. Verify what is actually running ────────────────────────────────────────
echo "==> Launching"
open "$INSTALLED"

for _ in $(seq 1 20); do
  if curl -s -m 2 http://127.0.0.1:8000/api/status >/dev/null 2>&1; then break; fi
  sleep 1
done

echo ""
echo "==> Verification"

RUNNING="$(pgrep -fl "$APP_NAME" | grep -c "Contents/MacOS" || true)"
echo "    processes:     $RUNNING  (expect 3: app + sidecar bootloader + sidecar)"

pgrep -fl "$APP_NAME" | grep "Contents/MacOS" | grep -v "^.*$INSTALLED" >/dev/null 2>&1 \
  && echo "    WARNING: a process is running from outside $INSTALLED" \
  || echo "    all processes run from $INSTALLED"

if [ -x "$LSREGISTER" ]; then
  REG="$("$LSREGISTER" -dump 2>/dev/null | grep -oE "/[^ ]*$APP_NAME" | sort -u | wc -l | tr -d ' ')"
  echo "    registrations: $REG  (expect 1)"
fi

if curl -s -m 3 http://127.0.0.1:8000/api/status >/dev/null 2>&1; then
  echo "    backend:       up"
  echo "    status:        $(curl -s -m 3 http://127.0.0.1:8000/api/status)"
  ROUTES="$(curl -s -m 3 http://127.0.0.1:8000/openapi.json \
    | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["paths"]))' 2>/dev/null || echo '?')"
  echo "    routes:        $ROUTES"
else
  echo "    backend:       DID NOT COME UP"
  exit 1
fi

echo ""
echo "==> Installed and running. Connect on the Home tab to test."
