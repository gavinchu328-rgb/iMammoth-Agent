#!/usr/bin/env bash
# Run all skill display unit tests (no live API required).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== backend: thinking preserve =="
python3 scripts/test_thinking_preserve.py

echo "== backend: skill display pipeline =="
python3 scripts/test_skill_display_pipeline.py

echo "== backend: JSON UI sanitize =="
python3 scripts/test_json_ui_sanitize.py

echo "== backend: stream content filter =="
python3 scripts/test_stream_content_filter.py

echo "== backend: rich final answer =="
python3 scripts/test_rich_final_answer.py

echo "== backend: content filters decouple =="
python3 scripts/test_content_filters_decouple.py

echo "== backend: protein trailing final =="
python3 scripts/test_protein_trailing_final.py

echo "== backend: pocket final extract =="
python3 scripts/test_pocket_final_extract.py

echo "== backend: process log snapshot =="
python3 scripts/test_process_log_snapshot.py

echo "== frontend: skill routing =="
npx --yes tsx scripts/test_skill_routing.ts

echo "== frontend: skill display =="
cd frontend && npm run build -s
cd "$ROOT"
npx --yes tsx scripts/test_skill_display_frontend.ts

echo "== frontend: resolve display answer =="
npx --yes tsx scripts/test_resolve_display_answer.ts

echo ""
echo "All display unit tests passed."
