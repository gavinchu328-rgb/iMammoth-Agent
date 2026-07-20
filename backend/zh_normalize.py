"""英文思考 → 简体中文（写日志 / 读日志时调用）。"""

from __future__ import annotations

import re

import httpx

_ZH = re.compile(r"[\u4e00-\u9fff]")
_EN = re.compile(r"[A-Za-z]")
_URL = "http://127.0.0.1:8006/v1/chat/completions"
_MODEL = "Qwen3.6-35B-A3B"
_cache: dict[str, str] = {}


def is_mostly_english(text: str) -> bool:
    s = (text or "").strip()
    if len(s) < 8:
        return False
    en, cn = len(_EN.findall(s)), len(_ZH.findall(s))
    return en > 0 and en > cn * 1.2


async def to_zh(text: str) -> str:
    raw = (text or "").strip()
    if not raw or not is_mostly_english(raw):
        return raw
    key = raw[:1200]
    if key in _cache:
        return _cache[key]
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                _URL,
                json={
                    "model": _MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "把英文译成简洁中文，只输出译文。工具名/路径/代码可保留原文。",
                        },
                        {"role": "user", "content": key},
                    ],
                    "max_tokens": 512,
                    "temperature": 0,
                    "chat_template_kwargs": {"enable_thinking": False},
                },
            )
            resp.raise_for_status()
            out = (
                ((resp.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            ).strip()
            if out:
                _cache[key] = out
                return out
    except Exception:
        pass
    return raw


async def normalize_step_zh(step: dict) -> dict:
    """思考步骤若为英文则译成中文；其它步骤原样返回。"""
    if step.get("kind") != "thinking":
        return step
    text = (step.get("result") or step.get("input") or "").strip()
    if not text or not is_mostly_english(text):
        return step
    zh = await to_zh(text)
    out = dict(step)
    out["result"] = zh[:240]
    out["input"] = zh[:120]
    return out
