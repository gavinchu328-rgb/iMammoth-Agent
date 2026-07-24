#!/usr/bin/env python3
"""思考步骤在 polish/merge 后应保留完整 detail。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reply_rebuild import merge_live_steps, rebuild_reply_with_live_steps
from tool_summarize import polish_ai4drug_exec_step, polish_ai4drug_exec_steps

LONG_THINKING = (
    "用户希望做靶点发现。我需要调用 target_discovery 工具，"
    "查询非小细胞肺癌相关 targets，并整理 success 字段与 JSON 结果。\n"
    "第二段思考：比较 EGFR、KRAS 等候选靶点的证据强度。"
)


def test_polish_preserves_thinking() -> None:
    step = {
        "kind": "thinking",
        "title": "深度思考",
        "name": "深度思考",
        "input": LONG_THINKING[:300],
        "result": LONG_THINKING[:300],
        "detail": LONG_THINKING,
        "record_id": "rec-1",
        "thinking_seq": 0,
    }
    out = polish_ai4drug_exec_step(step)
    assert out["detail"] == LONG_THINKING, out["detail"]
    batch = polish_ai4drug_exec_steps([step])
    assert batch[0]["detail"] == LONG_THINKING


def test_merge_keeps_longer_thinking() -> None:
    short = {
        "kind": "thinking",
        "record_id": "rec-1",
        "thinking_seq": 0,
        "detail": "短",
        "result": "短",
        "input": "短",
    }
    long = {
        "kind": "thinking",
        "record_id": "rec-1",
        "thinking_seq": 0,
        "detail": LONG_THINKING,
        "result": LONG_THINKING[:300],
        "input": LONG_THINKING[:300],
    }
    merged = merge_live_steps([long, short])
    assert len(merged) == 1
    assert merged[0]["detail"] == LONG_THINKING


def test_rebuild_reply_keeps_thinking_detail() -> None:
    steps = [
        {
            "kind": "thinking",
            "title": "深度思考",
            "name": "深度思考",
            "status": "done",
            "detail": LONG_THINKING,
            "result": LONG_THINKING[:300],
            "input": LONG_THINKING[:300],
            "thinking_seq": 0,
        }
    ]
    reply = rebuild_reply_with_live_steps("## 最终回答\n\n完成。", steps)
    assert LONG_THINKING in reply
    assert "第二段思考" in reply


def test_thinking_not_billable_mcp() -> None:
    from tool_summarize import is_billable_action_step, is_mcp_tool_step

    step = {
        "kind": "thinking",
        "name": "深度思考",
        "title": "深度思考",
        "detail": "将用 mcporter 调用 pocket_prediction",
    }
    assert not is_mcp_tool_step(step)
    assert not is_billable_action_step(step)


def test_early_ligand_final() -> None:
    from reply_rebuild import synthesize_early_final_from_steps

    steps = [
        {
            "kind": "tool",
            "name": "配体准备",
            "title": "配体准备",
            "status": "done",
            "result": "已制备 1 个配体",
            "detail": "EGFR_3W2S_pocket1_mol0",
        }
    ]
    block = synthesize_early_final_from_steps(steps, "配体准备")
    assert "配体准备" in block
    assert "EGFR_3W2S_pocket1_mol0" in block


def main() -> None:
    test_polish_preserves_thinking()
    test_merge_keeps_longer_thinking()
    test_rebuild_reply_keeps_thinking_detail()
    test_thinking_not_billable_mcp()
    test_early_ligand_final()
    print("thinking_preserve OK")


if __name__ == "__main__":
    main()
