#!/usr/bin/env python3
"""Regression: retrosynthesis session e1b7bcf3 must not produce messy final/process."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from content_filters import is_synthesized_step_dump_final
from reply_rebuild import (
    build_process_section_markdown,
    extract_final_answer,
    merge_live_steps,
    rebuild_reply_with_live_steps,
    resolve_final_answer,
)
from tool_summarize import polish_ai4drug_exec_steps

LOG = ROOT / "process_logs/2026-07-24/e1b7bcf3-87d8-42d2-af5d-e455109b7ecd.jsonl"


def _load() -> tuple[list[dict], str]:
    steps: list[dict] = []
    raw = ""
    for line in LOG.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("<<<MAMMOTH"):
            continue
        obj = json.loads(line)
        if obj.get("type") == "step":
            steps.append(obj)
        elif obj.get("type") == "mammoth_done":
            raw = obj.get("reply") or ""
    return steps, raw


def main() -> None:
    steps, raw = _load()
    merged = merge_live_steps(steps)
    polished = polish_ai4drug_exec_steps(merged, reply=raw)
    rebuilt = rebuild_reply_with_live_steps(raw, polished, "逆合成分析")
    process_md = build_process_section_markdown(polished)
    final = resolve_final_answer(extract_final_answer(raw), polished, "逆合成分析")

    assert "深度思考" not in process_md, "thinking must not appear in process section"
    assert process_md.count("### 步骤") == 2, process_md
    assert "3D构象生成" in process_md
    assert "逆合成" in process_md
    assert "逆合成路线已生成（5 步）" not in final, final[:400]
    assert is_synthesized_step_dump_final(
        "**3D构象生成**\n\n- x\n\n**逆合成路线已生成（5 步）**\n\n- 输入摘要: foo"
    )
    assert "MCP 工具未能" in final or "未能找到" in final or "未找到合成路线" in final, final[:400]
    assert "- 输入摘要:" not in final, final[:400]
    assert "深度思考" not in rebuilt.split("## 最终回答", 1)[-1], rebuilt[-500:]

    print("ok: retrosynthesis reply heal")
    print("process steps:", process_md.count("### 步骤"))
    print("final head:", final[:120].replace("\n", " "))


if __name__ == "__main__":
    main()
