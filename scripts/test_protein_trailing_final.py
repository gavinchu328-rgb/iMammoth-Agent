#!/usr/bin/env python3
"""Regression: protein acquisition stream without ## 最终回答 must keep rich report."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reply_rebuild import extract_final_answer, rebuild_reply_with_live_steps  # noqa: E402
from reply_rebuild import merge_live_steps  # noqa: E402
from tool_summarize import polish_ai4drug_exec_steps  # noqa: E402

SESSION = "5007f138-c8ee-411b-99ef-e73f9b996d4d"
log = ROOT / "process_logs" / "2026-07-24" / f"{SESSION}.jsonl"

chunks: list[str] = []
steps: list[dict] = []
for line in log.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("<<<MAMMOTH_DONE>>>"):
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if row.get("type") == "delta" and row.get("content"):
        chunks.append(str(row["content"]))
    if row.get("type") == "step" and row.get("kind"):
        steps.append(row)

stream = "".join(chunks)
final = extract_final_answer(stream)
assert len(final) > 400, f"expected rich final, got {len(final)} chars: {final[:120]!r}"
assert "MinIO" in final
assert "| PDB ID |" in final or "1M17" in final

merged = polish_ai4drug_exec_steps(merge_live_steps(steps))
rebuilt = rebuild_reply_with_live_steps(stream, merged, skill_name="蛋白质获取")
assert "MinIO" in rebuilt
assert "**蛋白质获取**" not in rebuilt or "MinIO" in rebuilt
print("ok: protein acquisition trailing final preserved")
