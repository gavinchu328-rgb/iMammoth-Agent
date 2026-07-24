#!/usr/bin/env python3
"""后台进程 molecule JSON 应合并进分子设计步骤并生成可读最终回答。"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reply_rebuild import merge_live_steps, synthesize_final_from_steps
from tool_summarize import (
    _merge_poll_into_parent,
    _poll_carries_tool_result,
    polish_ai4drug_exec_steps,
)

SID = "25dd5943-4963-4506-936a-81d5098acbb7"
LOG = ROOT / "process_logs" / "2026-07-23" / f"{SID}.jsonl"


def main() -> None:
    raw_steps = []
    content_parts: list[str] = []
    for line in LOG.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "step":
            raw_steps.append({k: v for k, v in o.items() if k not in ("type", "ts")})
        elif o.get("type") == "delta":
            content_parts.append(o.get("content") or "")

    poll = next(s for s in raw_steps if s.get("name") == "后台进程" and '"molecules"' in (s.get("detail") or ""))
    assert _poll_carries_tool_result(poll), "poll should carry molecule_design result"

    parent = {"kind": "tool", "title": "分子设计", "name": "分子设计", "status": "running", "result": "", "detail": ""}
    out = [parent]
    assert _merge_poll_into_parent(out, poll)
    assert "mol" in (out[0].get("detail") or "").lower() or "chembl" in (out[0].get("detail") or "").lower()

    merged = polish_ai4drug_exec_steps(
        merge_live_steps(raw_steps),
        reply="".join(content_parts),
        raw_steps=raw_steps,
    )
    md = next(s for s in merged if s.get("name") == "分子设计")
    detail = md.get("detail") or ""
    assert "已生成" in (md.get("result") or ""), md.get("result")
    assert "mol" in detail.lower() or "chembl" in detail.lower(), detail[:200]

    final = synthesize_final_from_steps(merged)
    assert "分子设计" in final or "候选分子" in final, final[:300]
    assert '"pocket_id":' not in final, final[:300]
    print("ok: molecule design display")


if __name__ == "__main__":
    main()
