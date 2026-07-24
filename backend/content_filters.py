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


def is_final_answer_unusable(text: str) -> bool:
    """最终回答是否应丢弃并改用步骤合成兜底（规则比过程更宽松）。"""
    t = (text or "").strip()
    if not t:
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
    return t.strip()


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
    score = len(t)
    if has_rich_markdown_report(t):
        score += 10_000
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
