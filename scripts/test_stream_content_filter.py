#!/usr/bin/env python3
"""Client stream filter suppresses process dumps and JSON fragments."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from stream_content_filter import ClientStreamFilter


def main() -> None:
    gate = ClientStreamFilter()
    out = []
    for chunk in [
        "## 分析过程",
        "\n\n### 步骤 1",
        '\n- 详情: {"success": true',
        ',"molecules":[]}',
        "\n\n## 最终回答",
        "\n\n已生成 3 个分子",
    ]:
        out.append(gate.feed(chunk))
    joined = "".join(out)
    assert "## 分析过程" not in joined
    assert '"success"' not in joined
    assert "已生成 3 个分子" in joined

    gate2 = ClientStreamFilter()
    collapsed = (
        "##分析过程-工具数:1###步骤1·3D构象生成-类型:工具-状态:进行中"
        "-名称:ai4drug__conformer_generation-输入摘要:test"
    )
    assert gate2.feed(collapsed) == ""
    assert gate2.feed("\n\n##最终回答\n\n已生成 1 个分子构象") == "已生成 1 个分子构象"

    gate3 = ClientStreamFilter()
    gate3.feed("## 最终回答\n\n**结果**\n")
    tail = gate3.feed("\n## 分析过程\n- 工具数: 1")
    assert "分析过程" not in tail
    assert "工具数" not in tail

    g4 = ClientStreamFilter()
    out4 = []
    for c in [
        "## 分析**标题**\n- line\n",
        "\n## 最终回答\n\n真正回答",
    ]:
        out4.append(g4.feed(c))
    joined4 = "".join(out4)
    assert joined4 == "真正回答", joined4

    gate5 = ClientStreamFilter()
    partial: list[str] = []
    for c in ["## ", "分析", "过程\n\n### 步骤 1", "\n\n## 最终回答\n\n完成"]:
        partial.append(gate5.feed(c))
    joined5 = "".join(partial)
    assert "分析" not in joined5 or "完成" in joined5
    assert joined5.strip() == "完成", joined5

    gate6 = ClientStreamFilter()
    assert gate6.feed("发现 API 返回了自动生成的 session_id，但指令要求使用猛犸 UUID。需要用正确 session_id 重试。") == ""
    assert gate6.feed(" 📋") == ""
    out6 = gate6.feed("\n\n## 最终回答\n\n### 📋 吉非替尼 ADMET 报告\n\n| QED | 0.8 |")
    assert "session_id" not in out6
    assert "吉非替尼" in out6

    print("ok: client stream filter")


if __name__ == "__main__":
    main()
