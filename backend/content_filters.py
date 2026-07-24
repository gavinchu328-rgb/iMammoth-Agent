"""Separate filtering rules for process steps vs final answers.

过程信息（步骤列表、工具中间态）与最终结果（模型报告）使用不同规则，
避免过程侧启发式误伤最终输出。
"""

from __future__ import annotations

import re

from tool_summarize import strip_process_runtime_noise


def has_rich_markdown_report(text: str) -> bool:
    """Substantial markdown report (tables/sections), not a collapsed template."""
    t = (text or "").strip()
    if len(t) < 120:
        return False
    headers = len(re.findall(r"^#{1,6}\s+\S", t, re.MULTILINE))
    has_table = "|" in t and "---" in t
    if headers >= 2 and has_table:
        return True
    if headers >= 1 and has_table and len(t) >= 200:
        return True
    return False


def is_process_template_dump(text: str) -> bool:
    """Collapsed ## 分析过程 / 步骤模板，仅用于过程区判断。"""
    t = (text or "").strip()
    if not t:
        return True
    compact = t.replace(" ", "")
    if "##分析过程" in compact or "###步骤" in compact:
        return True
    if any(
        token in t
        for token in (
            "-类型:",
            "- 类型:",
            "等待执行",
            "等待返回",
            "状态:进行中",
            "状态:等待",
            "-状态:进行中",
            "-状态:等待",
        )
    ):
        return True
    if t.count("✅") >= 2 and not any(
        marker in t for marker in ("QED", "评分", "pocket", "PDB", "|", "对接", "hERG", "BBB")
    ):
        return True
    return False


def extract_embedded_skill_report(raw: str) -> str:
    """从误入过程步骤的正文中抽出技能报告块。"""
    text = raw or ""
    m = re.search(
        r"(?:\*\*逆合成分析结果：[^*]+\*\*|\*\*逆合成分析未找到合成路线\*\*)"
        r"[\s\S]*?(?=\n- 输入摘要:|\n- 结果摘要:|\n###\s*步骤|\n##\s*(?:最终回答|分析过程)|\Z)",
        text,
    )
    if not m:
        return ""
    body = sanitize_final_answer_text(m.group(0).strip())
    body = re.sub(r"^- 详情:\s*", "", body, flags=re.MULTILINE).strip()
    return body


def is_synthesized_step_dump_final(text: str) -> bool:
    """步骤字段拼出来的伪最终回答（输入摘要/结果摘要/详情列表）。"""
    t = (text or "").strip()
    if not t:
        return False
    if t.startswith("**逆合成分析结果") or t.startswith("**逆合成分析未找到"):
        return False
    field_hits = len(re.findall(r"^-\s*(?:输入摘要|结果摘要|详情):", t, re.MULTILINE))
    if field_hits >= 2:
        return True
    if "逆合成路线已生成" in t and any(
        token in t for token in ("未能找到", "no synthesis routes", "MCP 工具未能")
    ):
        return True
    if t.startswith("**3D构象生成**") and "逆合成路线已生成" in t:
        return True
    return False


def is_final_answer_unusable(text: str) -> bool:
    """最终回答是否应丢弃并改用步骤合成兜底（规则比过程更宽松）。"""
    t = (text or "").strip()
    if not t:
        return True
    if is_synthesized_step_dump_final(t):
        return True
    if has_rich_markdown_report(t):
        return False
    if is_process_template_dump(t):
        return True
    if '"pocket_id":' in t and "|" not in t and len(t) < 200:
        return True
    if '"molecules":' in t and "|" not in t and len(t) < 200:
        return True
    return False


def sanitize_process_step_text(text: str) -> str:
    """过程步骤字段：去除 exec 中间态、运行噪声。"""
    return strip_process_runtime_noise(text or "")


_EMOJI_BETWEEN = r"(?:[\U0001F300-\U0001FAFF\U00002600-\U000027BF]\s*)*"


def _strip_orphan_emoji_lines(text: str) -> str:
    lines = (text or "").split("\n")
    kept = [
        ln
        for ln in lines
        if not re.fullmatch(r"\s*[\U0001F300-\U0001FAFF\U00002600-\U000027BF]+\s*", ln)
    ]
    return "\n".join(kept)


def _strip_structured_json_appendix(text: str) -> str:
    """Remove model-appended tool JSON blocks from user-facing final answers."""
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(
        rf"\n*(?:#{{1,3}}\s*)?{_EMOJI_BETWEEN}(?:\*{{1,2}})?完整结构化数据:?(?:\*{{1,2}})?\s*\n*```json\s*[\s\S]*?```",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(
        r"\n*```json\s*\{[\s\S]*?\"session_id\"[\s\S]*?```\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    t = re.sub(
        rf"\n*#{{1,3}}\s*{_EMOJI_BETWEEN}完整结构化数据\s*$",
        "",
        t,
        flags=re.IGNORECASE,
    ).strip()
    return _strip_orphan_emoji_lines(t)


def sanitize_final_answer_text(text: str) -> str:
    """最终回答：仅去掉误入的过程段/告警尾注，不套用过程噪声过滤。"""
    t = (text or "").strip()
    if not t:
        return ""
    for marker in ("## 分析过程", "##分析过程"):
        idx = t.find(marker)
        if idx >= 0:
            t = t[:idx].strip()
    noise = t.find("\n⚠️")
    if noise >= 0:
        t = t[:noise].strip()
    exec_fail = t.find("\n⚠️ 🛠️ Exec failed:")
    if exec_fail >= 0:
        t = t[:exec_fail].strip()
    return _strip_structured_json_appendix(t)


# Back-compat alias used by tests / gradual migration
def is_low_quality_final_answer(text: str) -> bool:
    return is_final_answer_unusable(text)


_TRAILING_FINAL_START = re.compile(
    r"(?:"
    r"✅\s*\*\*第\s*\d+\s*步"
    r"|✅\s*\*\*步骤\s*\d+"
    r"|(?:^|\n)##\s*结果摘要"
    r"|(?:^|\n)###\s*🔬"
    r"|(?:^|\n)#\s+🔬"
    r"|(?:^|\n)###\s*🫁"
    r")",
    re.MULTILINE,
)
_PROCESS_HEAD = re.compile(r"##\s*分析过程|##分析过程")


def _looks_like_live_process_chunk(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if "### 步骤" in t and "- 类型:" in t and "- 状态:" in t:
        return True
    if "- 工具数:" in t and "### 步骤" in t:
        return True
    return False


def _final_answer_quality_score(text: str) -> int:
    t = (text or "").strip()
    if not t:
        return 0
    score = min(len(t), 2000)
    if is_synthesized_step_dump_final(t):
        score -= 800
    if has_rich_markdown_report(t):
        score += 10_000
    if "MCP 工具未能" in t or "未能找到合成路线" in t:
        score += 500
    # 步骤合成兜底（**技能名** 开头短列表）权重低于模型报告
    if re.match(r"^\*\*[^*]+\*\*\s*\n\s*[-|]", t) and len(t) < 400:
        score -= 2_000
    return score


def extract_trailing_model_final(raw: str) -> str:
    """Model prose after embedded process blocks when ## 最终回答 is missing."""
    text = (raw or "").strip()
    if not text:
        return ""

    candidates: list[str] = []
    for m in _TRAILING_FINAL_START.finditer(text):
        tail = sanitize_final_answer_text(text[m.start() :])
        if tail and not is_process_template_dump(tail) and not is_final_answer_unusable(tail):
            candidates.append(tail)
    if candidates:
        return max(candidates, key=len)

    remainder_parts: list[str] = []
    for seg in _PROCESS_HEAD.split(text):
        part = seg.strip()
        if not part or _looks_like_live_process_chunk(part) or is_process_template_dump(part):
            continue
        remainder_parts.append(part)
    remainder = sanitize_final_answer_text("\n\n".join(remainder_parts))
    if remainder and not is_process_template_dump(remainder) and not is_final_answer_unusable(remainder):
        return remainder
    return ""
