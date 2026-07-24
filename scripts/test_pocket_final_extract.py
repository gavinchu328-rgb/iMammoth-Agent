#!/usr/bin/env python3
"""Pocket prediction: prefer last ## 最终回答 segment, not early synthesis glue."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reply_rebuild import extract_final_answer, rebuild_reply_with_live_steps, merge_live_steps  # noqa: E402
from tool_summarize import polish_ai4drug_exec_steps  # noqa: E402

SESSION = "112f71e2-3163-46f6-9909-aaf54e710c0c"
log = ROOT / "process_logs" / "2026-07-24" / f"{SESSION}.jsonl"

chunks: list[str] = []
steps: list[dict] = []
done = ""
for line in log.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        continue
    if row.get("type") == "delta" and row.get("content"):
        chunks.append(str(row["content"]))
    if row.get("type") == "step" and row.get("kind"):
        steps.append(row)
    if row.get("type") == "mammoth_done":
        done = str(row.get("reply") or "")

stream = "".join(chunks)
stream_final = extract_final_answer(stream)
saved_final = extract_final_answer(done)

assert "P2Rank" in stream_final, stream_final[:200]
assert "中心" in stream_final or "中心坐标" in stream_final
assert stream_final.startswith("**口袋预测**") is False
assert len(stream_final) < 2500, f"glued early+late final too long: {len(stream_final)}"

merged = polish_ai4drug_exec_steps(merge_live_steps(steps))
rebuilt = rebuild_reply_with_live_steps(stream, merged, skill_name="口袋预测")
rebuilt_final = extract_final_answer(rebuilt)
assert "P2Rank" in rebuilt_final
assert abs(len(rebuilt_final) - len(saved_final)) < 200, (len(rebuilt_final), len(saved_final))

print("ok: pocket final extract prefers model segment")
