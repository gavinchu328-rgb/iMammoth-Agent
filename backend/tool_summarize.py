"""把 OpenClaw 原始工具调用整理成友好的中文摘要（不暴露完整路径）。"""

from __future__ import annotations

import json
import re
from typing import Any


_PATH_RE = re.compile(
    r"(?:~|/home/|/data\d?/|/tmp/|\./)[^\s\"']+",
)
_SKILL_MD_RE = re.compile(
    r"(?:skills|skill)[/\\]([^/\\]+)[/\\]SKILL\.md",
    re.I,
)
_CHEM_CALC_RE = re.compile(
    r"chemistry-calc\s+(\w+)\s+[\"']?([^\s\"']+)",
    re.I,
)


def strip_paths(text: str) -> str:
    """隐藏绝对路径，保留文件名或技能名。"""
    s = text or ""

    def repl(m: re.Match[str]) -> str:
        p = m.group(0)
        skill = _SKILL_MD_RE.search(p)
        if skill:
            return f"技能「{skill.group(1)}」"
        # keep basename
        base = p.rstrip("/").split("/")[-1]
        return base or "文件"

    return _PATH_RE.sub(repl, s)


def _friendly_read(arguments: dict) -> tuple[str, str, str]:
    path = str(arguments.get("path") or arguments.get("file") or "")
    skill = _SKILL_MD_RE.search(path)
    if skill:
        sid = skill.group(1)
        return (
            f"读取技能「{sid}」",
            sid,
            "读取技能说明",
        )
    name = path.rstrip("/").split("/")[-1] if path else "文件"
    return (f"读取「{name}」", "read", f"读取 {name}")


def _friendly_exec(arguments: dict) -> tuple[str, str, str]:
    cmd = str(arguments.get("command") or "")
    chem = _CHEM_CALC_RE.search(cmd)
    if chem:
        action, arg = chem.group(1), chem.group(2)
        # SMILES-like or formula
        if action.lower() == "properties":
            return (
                "化学性质计算",
                "chemistry-calculation (properties)",
                f'SMILES "{arg}"，查询分子量',
            )
        return (
            f"化学计算 · {action}",
            f"chemistry-calculation ({action})",
            f'输入 "{arg}"',
        )
    # generic: drop paths, keep short command gist
    cleaned = strip_paths(cmd)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 80:
        cleaned = cleaned[:77] + "…"
    return ("执行命令", "exec", cleaned or "执行操作")


def _friendly_generic(name: str, arguments: Any) -> tuple[str, str, str]:
    if isinstance(arguments, dict):
        # prefer high-signal keys
        for key in ("query", "q", "text", "prompt", "smiles", "formula", "url", "name"):
            if key in arguments and arguments[key]:
                val = str(arguments[key])[:120]
                return (name, name, strip_paths(val))
        blob = strip_paths(json.dumps(arguments, ensure_ascii=False))[:120]
        return (name, name, blob)
    return (name, name, strip_paths(str(arguments))[:120])


def friendly_tool_step(tool_name: str, arguments: Any) -> dict[str, str]:
    """返回 title / name / input，用于过程面板展示。"""
    name = (tool_name or "tool").strip()
    args = arguments if isinstance(arguments, dict) else {}

    if name in ("read", "Read", "read_file"):
        title, display_name, inp = _friendly_read(args)
    elif name in ("exec", "bash", "shell", "Bash"):
        title, display_name, inp = _friendly_exec(args)
    else:
        title, display_name, inp = _friendly_generic(name, arguments if arguments is not None else args)

    return {
        "title": title,
        "name": display_name,
        "input": inp,
    }


def summarize_tool_result(tool_name: str, raw: str) -> dict[str, str]:
    """把工具原始输出压成「结果摘要 + 详情」，对齐 MatVenus 的 输出 区。"""
    text = (raw or "").strip()
    if not text:
        return {"result": "（无输出）", "detail": ""}

    # chemistry-calc JSON
    if text.startswith("{") and ("property_list" in text or "molecular_weight" in text):
        try:
            data = json.loads(text)
            props = data.get("property_list") or []
            bits = []
            for p in props[:6]:
                label = p.get("label") or p.get("key") or ""
                val = p.get("value")
                unit = p.get("unit") or ""
                if label and val is not None:
                    bits.append(f"{label} {val}{' ' + unit if unit else ''}".strip())
            if bits:
                return {
                    "result": "；".join(bits[:3]),
                    "detail": "\n".join(bits),
                }
        except json.JSONDecodeError:
            pass
        mw = re.search(r'"molecular_weight"\s*:\s*([0-9.]+)', text)
        if mw:
            return {"result": f"分子量 {mw.group(1)} g/mol", "detail": text[:500]}

    # skill markdown
    if text.startswith("---") and "name:" in text[:80]:
        m = re.search(r"^name:\s*([^\n]+)", text, re.M)
        d = re.search(r'^description:\s*"?([^"\n]+)"?', text, re.M)
        name = (m.group(1).strip() if m else tool_name) or "skill"
        desc = (d.group(1).strip() if d else "")[:120]
        return {
            "result": f"已读取技能「{name}」说明",
            "detail": desc or text[:300],
        }

    cleaned = strip_paths(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    summary = cleaned[:120] + ("…" if len(cleaned) > 120 else "")
    return {"result": summary or "执行完成", "detail": cleaned[:800]}
