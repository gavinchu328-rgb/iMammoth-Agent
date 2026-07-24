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
assert picked == model_short, "usable short model kept (no step merge)"

picked_empty = _merge_final_answer("", [step])
assert "|" in picked_empty and "pocket1" in picked_empty, picked_empty[:200]

raw = f"## 分析过程\n\nfoo\n\n## 最终回答\n\n{model_short}\n"
rebuilt = rebuild_reply_with_live_steps(raw, [step])
assert model_short in rebuilt, "model final preserved in rebuild"
assert "## 分析过程" in rebuilt and "## 最终回答" in rebuilt
assert "EGFR_3W2S_pocket1" in rebuilt, "pocket id appears in process section"
print("ok: rich final answer")

# Regression: markdown report + JSON appendix must not be treated as low-quality JSON leak.
from reply_rebuild import _is_low_quality_final_answer, extract_final_answer  # noqa: E402

rich_report = """### 🔬 肺癌药物靶点发现

#### Top 10 靶点

| 排名 | 靶点 | 分数 |
|:---:|:---:|:---:|
| 1 | **EGFR** | 0.888 |

#### 关键洞察

- EGFR 是最强关联靶点。

```json
{"session_id": "abc", "tool": "target_discovery", "targets": [{"gene": "EGFR"}]}
```
"""
assert not _is_low_quality_final_answer(rich_report), "rich report misclassified"
merged_td = _merge_final_answer(rich_report, [step], skill_name="靶点发现")
assert "EGFR" in merged_td and "|" in merged_td
assert "**靶点发现**" not in merged_td or rich_report in merged_td

raw_td = f"## 最终回答\n\n{rich_report}\n"
rebuilt_td = rebuild_reply_with_live_steps(raw_td, [step], skill_name="靶点发现")
assert "Top 10" in rebuilt_td
assert "0.888" in rebuilt_td
print("ok: target discovery rich report preserved")
