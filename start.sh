#!/bin/bash
set -e
cd "$(dirname "$0")"

# Load Rust/Cargo into PATH
source "$HOME/.cargo/env" 2>/dev/null || true

echo "Installing frontend dependencies..."
cd frontend && npm install --silent

echo "Launching KiroshiOS (Tauri menu bar app)..."
echo "  • Vite dev server starts automatically"
echo "  • Python backend (api.py) is spawned by Tauri on launch"
npm run tauri:dev
