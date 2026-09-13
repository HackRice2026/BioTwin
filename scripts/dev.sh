#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --frozen
npm ci --prefix frontend
uv run uvicorn core.api:app --host 0.0.0.0 --port 8000 --no-access-log &
BIOTWIN_API_PID=$!
trap 'kill "$BIOTWIN_API_PID" 2>/dev/null || true' EXIT
npm run dev --prefix frontend
