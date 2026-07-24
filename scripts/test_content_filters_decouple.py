#!/usr/bin/env python3
"""Process vs final answer filters must not cross-contaminate."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from content_filters import (  # noqa: E402
    has_rich_markdown_report,
    is_final_answer_unusable,
    is_process_template_dump,
    sanitize_final_answer_text,
    sanitize_process_step_text,
)

# Process template dump — only process rules
collapsed = "##分析过程-工具数:1###步骤1·口袋预测-类型:工具-状态:进行中"
assert is_process_template_dump(collapsed)
assert is_final_answer_unusable(collapsed)

# Rich report with JSON appendix — final rules must keep it (not misclassified as JSON leak)
rich = """### Top 10 靶点

| 排名 | 靶点 | 分数 |
|:---:|:---:|:---:|
| 1 | **EGFR** | 0.888 |
| 2 | **ALK** | 0.812 |

#### 关键洞察

- EGFR 是最强关联靶点，建议优先验证。

```json
{"tool": "target_discovery", "targets": [{"gene": "EGFR"}]}
```
"""
assert has_rich_markdown_report(rich)
assert not is_final_answer_unusable(rich)

# Bare JSON leak — final unusable
bare_json = '{"pocket_id": "EGFR_3W2S_pocket1", "score": 0.82}'
assert is_final_answer_unusable(bare_json)

# sanitize_final_answer_text strips process section leak, not report body
mixed = f"简短结论\n\n## 分析过程\n\n### 步骤 1\n"
assert sanitize_final_answer_text(mixed) == "简短结论"

# Process sanitizer strips runtime polling noise (not final-answer rules)
noisy = "命令仍在后台运行\n请等待工具返回完整结果"
assert sanitize_process_step_text(noisy) == ""

ligand_final = """✅ **吉非替尼配体准备完成！**

| 步骤 | 状态 |
| --- | --- |
| 1. 构象生成 | ✅ |

**完整结构化数据:**
```json
{"session_id": "abc", "molecule_id": "mol0"}
```
"""
stripped = sanitize_final_answer_text(ligand_final)
assert "完整结构化数据" not in stripped
assert "```json" not in stripped
assert "构象生成" in stripped

emoji_appendix = """### 报告

| 指标 | 值 |
| --- | --- |
| QED | 0.8 |

### 📋 完整结构化数据
```json
{"session_id": "abc", "tool": "molecule_evaluation"}
```
"""
stripped_emoji = sanitize_final_answer_text(emoji_appendix)
assert "完整结构化数据" not in stripped_emoji
assert "```json" not in stripped_emoji
assert "QED" in stripped_emoji
assert not stripped_emoji.rstrip().endswith("📋")

print("ok: content filters decouple")
