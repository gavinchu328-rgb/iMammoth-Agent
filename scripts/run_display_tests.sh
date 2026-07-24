#!/usr/bin/env bash
# Run all skill display unit tests (no live API required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== backend: skill display pipeline =="
python3 scripts/test_skill_display_pipeline.py

echo "== backend: JSON UI sanitize =="
python3 scripts/test_json_ui_sanitize.py

echo "== backend: stream content filter =="
python3 scripts/test_stream_content_filter.py

echo "== frontend: skill display =="
cd frontend && npm run build -s
cd "$ROOT"
npx --yes tsx scripts/test_skill_display_frontend.ts

echo ""
echo "All display unit tests passed."
