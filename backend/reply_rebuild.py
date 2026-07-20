"""Rebuild assistant process markdown from live OpenClaw steps."""

from __future__ import annotations

from typing import Any

from tool_summarize import strip_paths


def extract_final_answer(reply: str) -> str:
    raw = (reply or "").strip()
    idx = raw.find("## 最终回答")
    if idx >= 0:
        text = raw[idx + len("## 最终回答") :].strip()
        noise = text.find("\n⚠️")
        if noise >= 0:
            text = text[:noise].strip()
        return text
    if "## 分析过程" in raw:
        return ""
    return raw


def merge_live_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by tool_call_id / record_id+kind, keep order.

    toolResult 回填时保留原 title/name/input，只更新 status/result/detail。
    """
    out: list[dict[str, Any]] = []
    by_tool: dict[str, int] = {}
    by_rec: dict[str, int] = {}
    for step in steps:
        tid = step.get("tool_call_id")
        if tid:
            if tid in by_tool:
                prev = out[by_tool[tid]]
                if step.get("is_result_update"):
                    out[by_tool[tid]] = {
                        **prev,
                        "status": step.get("status") or "done",
                        "result": step.get("result") or prev.get("result") or "",
                        "detail": step.get("detail") or prev.get("detail") or "",
                    }
                else:
                    out[by_tool[tid]] = {**prev, **step}
                continue
            by_tool[tid] = len(out)
            out.append(dict(step))
            continue
        rid = step.get("record_id")
        kind = step.get("kind")
        key = f"{rid}:{kind}" if rid else None
        if key and key in by_rec:
            out[by_rec[key]] = {**out[by_rec[key]], **step}
            continue
        if key:
            by_rec[key] = len(out)
        out.append(dict(step))
    return out


def rebuild_reply_with_live_steps(raw_reply: str, live_steps: list[dict[str, Any]]) -> str:
    """Prefer full live thinking/tool trail; keep model's final answer."""
    steps = merge_live_steps(live_steps)
    final = extract_final_answer(raw_reply)
    if not steps:
        return raw_reply

    tool_count = sum(1 for s in steps if s.get("kind") == "tool")
    lines = [
        "## 分析过程",
        f"- 工具数: {tool_count}",
        "",
    ]
    for i, step in enumerate(steps, start=1):
        kind = step.get("kind")
        is_tool = kind == "tool"
        title = (step.get("title") or step.get("name") or ("工具" if is_tool else "深度思考")).strip()
        name = (step.get("name") or "").strip()
        if name and name == title:
            name = title if is_tool else ""
        status = "已执行"
        inp = strip_paths((step.get("input") or "").strip())
        result = strip_paths((step.get("result") or "").strip())
        lines.append(f"### 步骤 {i} · {title}")
        lines.append(f"- 类型: {'工具' if is_tool else '思考'}")
        lines.append(f"- 状态: {status}")
        lines.append(f"- 名称: {name or title}")
        lines.append(f"- 输入摘要: {inp}")
        lines.append(f"- 结果摘要: {result}")
        detail = strip_paths((step.get("detail") or "").strip())
        lines.append(f"- 详情: {detail}")
        lines.append("")

    lines.append("## 最终回答")
    lines.append("")
    lines.append(final or raw_reply.strip())
    return "\n".join(lines).strip() + "\n"
