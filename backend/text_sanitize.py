"""用户可见文案清洗（品牌名、中间态提示等）。"""

from __future__ import annotations

import re

_INTERIM_STATUS = re.compile(
    r"正在通过\s*(?:OpenClaw\s*Agent|猛犸智能体)\s*处理您的请求[.…]*\s*",
    re.IGNORECASE,
)

_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("正在通过 OpenClaw Agent 处理您的请求", "猛犸智能体正在处理您的请求…"),
    ("正在通过 OpenClaw Agent 处理您的请求...", "猛犸智能体正在处理您的请求…"),
    ("正在通过 OpenClaw Agent 处理您的请求…", "猛犸智能体正在处理您的请求…"),
    ("OpenClaw Agent", "猛犸智能体"),
)


def sanitize_user_facing_text(text: str) -> str:
    if not text:
        return text
    out = text
    for old, new in _REPLACEMENTS:
        out = out.replace(old, new)
    out = _INTERIM_STATUS.sub("", out)
    out = out.replace("[[reply_to_current]]", "").strip()
    return out


def is_interm_status_only(text: str) -> bool:
    """是否为仅含「正在处理」的中间态占位，可忽略不展示。"""
    t = sanitize_user_facing_text(text).strip()
    if not t:
        return True
    return t in {
        "猛犸智能体正在处理您的请求…",
        "猛犸智能体正在处理您的请求...",
        "猛犸智能体正在处理您的请求",
    }
