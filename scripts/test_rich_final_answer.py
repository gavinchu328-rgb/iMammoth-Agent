#!/usr/bin/env python3
"""Rich final answer should beat short model summary."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reply_rebuild import _merge_final_answer, rebuild_reply_with_live_steps  # noqa: E402
from tool_summarize import polish_ai4drug_exec_step  # noqa: E402

payload = {
    "success": True,
    "data": {
        "tool": "pocket_prediction",
        "pockets": [
            {"pocket_id": "EGFR_3W2S_pocket1", "score": 0.82, "probability": 0.91},
            {"pocket_id": "EGFR_3W2S_pocket2", "score": 0.71, "probability": 0.85},
        ],
    },
}
step = polish_ai4drug_exec_step(
    {
        "kind": "tool",
        "title": "口袋预测",
        "name": "口袋预测",
        "status": "done",
        "result": json.dumps(payload),
        "detail": json.dumps(payload),
        "tool_call_id": "tid-pocket",
    }
)
model_short = "已完成口袋预测，EGFR 上识别到 2 个潜在结合口袋。"
picked = _merge_final_answer(model_short, [step])
assert "|" in picked and "pocket1" in picked, picked[:200]

raw = f"## 分析过程\n\nfoo\n\n## 最终回答\n\n{model_short}\n"
rebuilt = rebuild_reply_with_live_steps(raw, [step])
assert "EGFR_3W2S_pocket1" in rebuilt
assert rebuilt.count("| --- |") >= 1
print("ok: rich final answer")
