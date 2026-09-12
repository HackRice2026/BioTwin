#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
BIOTWIN_SCHEMA_CHECK=$(mktemp -d)
trap 'rm -rf "$BIOTWIN_SCHEMA_CHECK"' EXIT
cp shared/schemas/schema.json "$BIOTWIN_SCHEMA_CHECK/schema.json"
cp frontend/src/contracts.ts "$BIOTWIN_SCHEMA_CHECK/contracts.ts"
uv run python -m shared.scripts.export_schema
npm run types --prefix frontend
diff -u "$BIOTWIN_SCHEMA_CHECK/schema.json" shared/schemas/schema.json
diff -u "$BIOTWIN_SCHEMA_CHECK/contracts.ts" frontend/src/contracts.ts
