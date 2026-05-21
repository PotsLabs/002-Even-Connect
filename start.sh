#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "Building React frontend..."
cd frontend && npm install --silent && npm run build
cd ..

echo "Starting EvenConnect on http://localhost:8000"
source venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000
