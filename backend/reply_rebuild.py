"""Rebuild assistant markdown: process section and final answer are independent."""

from __future__ import annotations

import re

from typing import Any

from content_filters import (
    extract_trailing_model_final,
    has_rich_markdown_report,
    is_final_answer_unusable,
    sanitize_final_answer_text,
    sanitize_process_step_text,
)
from tool_summarize import (
    _prefer_longer_text,
    is_billable_action_step,
    strip_paths,
)
from skill_display import (
    should_emit_early_final,
    synthesize_final_from_steps,
)


def extract_final_answer(reply: str) -> str:
    raw = (reply or "").strip()
    markers = ("## 最终回答", "##最终回答")
    positions: list[tuple[int, int]] = []
    for marker in markers:
        start = 0
        while True:
            pos = raw.find(marker, start)
            if pos < 0:
                break
            positions.append((pos, len(marker)))
            start = pos + len(marker)

    if not positions:
        if "## 分析过程" in raw or "##分析过程" in raw:
            return extract_trailing_model_final(raw)
        return sanitize_final_answer_text(raw)

    section_markers = ("## 最终回答", "##最终回答", "## 分析过程", "##分析过程")

    def slice_final_segment(start_pos: int, marker_len: int) -> str:
        body = raw[start_pos + marker_len :]
        cut_at: list[int] = []
        for marker in section_markers:
            pos = body.find(marker)
            if pos > 0:
                cut_at.append(pos)
        if cut_at:
            body = body[: min(cut_at)]
        return sanitize_final_answer_text(body)

    candidates = [
        seg
        for pos, mlen in positions
        if (seg := slice_final_segment(pos, mlen)) and not is_final_answer_unusable(seg)
    ]
    if candidates:
        # 模型常在流末尾修订最终回答；取最后一个有效段，避免早期合成块与后续正文粘连。
        return candidates[-1]
    last_pos, last_len = positions[-1]
    return slice_final_segment(last_pos, last_len)


def resolve_final_answer(
    model_final: str,
    steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    """最终结果优先用模型流；仅当模型无有效正文时才用步骤合成兜底。"""
    final = sanitize_final_answer_text((model_final or "").strip())
    if final and not is_final_answer_unusable(final):
        return final

    synthesized = ""
    if not skill_name or should_emit_early_final(steps, skill_name):
        synthesized = (synthesize_final_from_steps(steps, skill_name) or "").strip()
    if synthesized:
        return synthesized
    return final


# Legacy name for tests
def _merge_final_answer(
    model_final: str,
    steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    return resolve_final_answer(model_final, steps, skill_name)


def _is_low_quality_final_answer(text: str) -> bool:
    return is_final_answer_unusable(text)


def _has_rich_markdown_report(text: str) -> bool:
    return has_rich_markdown_report(text)


def step_merge_key(step: dict[str, Any]) -> str | None:
    if step.get("record_id") == "__process_poll__" or step.get("tool_call_id") == "__process_poll__":
        return "internal:process_poll"
    tid = step.get("tool_call_id")
    if tid:
        return f"tid:{tid}"
    rid = step.get("record_id")
    kind = step.get("kind")
    if rid and kind == "thinking" and step.get("thinking_seq") is not None:
        return f"rec:{rid}:thinking:{step['thinking_seq']}"
    if rid and kind:
        return f"rec:{rid}:{kind}"
    return None


def merge_live_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe by tool_call_id / record_id+kind, keep order."""
    out: list[dict[str, Any]] = []
    by_tool: dict[str, int] = {}
    by_rec: dict[str, int] = {}
    for step in steps:
        tid = step.get("tool_call_id")
        if tid:
            if tid in by_tool:
                prev = out[by_tool[tid]]
                if step.get("is_result_update"):
                    name = str(step.get("name") or "")
                    title = str(step.get("title") or "")
                    keep_name = (
                        prev.get("name")
                        if name in ("exec", "执行命令", "命令工具", "bash", "shell", "tool")
                        else step.get("name")
                    )
                    keep_title = (
                        prev.get("title")
                        if title in ("exec", "执行命令", "命令工具", "bash", "shell", "tool", "")
                        else step.get("title")
                    )
                    out[by_tool[tid]] = {
                        **prev,
                        **step,
                        "name": keep_name or prev.get("name") or name,
                        "title": keep_title or prev.get("title") or title,
                        "status": step.get("status") or "done",
                        "result": _prefer_longer_text(
                            str(prev.get("result") or ""),
                            str(step.get("result") or ""),
                        ),
                        "detail": _prefer_longer_text(
                            str(prev.get("detail") or ""),
                            str(step.get("detail") or ""),
                        ),
                    }
                else:
                    merged = {**prev, **step}
                    merged["result"] = _prefer_longer_text(
                        str(prev.get("result") or ""),
                        str(step.get("result") or ""),
                    )
                    merged["detail"] = _prefer_longer_text(
                        str(prev.get("detail") or ""),
                        str(step.get("detail") or ""),
                    )
                    out[by_tool[tid]] = merged
                continue
            by_tool[tid] = len(out)
            out.append(dict(step))
            continue
        rid = step.get("record_id")
        kind = step.get("kind")
        if kind == "thinking" and step.get("thinking_seq") is not None:
            key = f"{rid}:thinking:{step['thinking_seq']}" if rid else None
        else:
            key = f"{rid}:{kind}" if rid else None
        if key and key in by_rec:
            prev = out[by_rec[key]]
            merged = {**prev, **step}
            if kind == "thinking":
                for field in ("detail", "result", "input"):
                    prev_val = str(prev.get(field) or "")
                    new_val = str(step.get(field) or "")
                    if len(prev_val) > len(new_val):
                        merged[field] = prev_val
            out[by_rec[key]] = merged
            continue
        if key:
            by_rec[key] = len(out)
        out.append(dict(step))
    return out


def _format_step_status(step: dict[str, Any]) -> str:
    st = str(step.get("status") or "done").lower()
    if st == "failed":
        return "失败"
    if st == "running":
        return "进行中"
    return "已执行"


def build_process_section_markdown(steps: list[dict[str, Any]]) -> str:
    """仅构建 ## 分析过程（过程过滤规则）。"""
    if not steps:
        return ""
    tool_count = sum(1 for s in steps if is_billable_action_step(s))
    lines = [
        "## 分析过程",
        f"- 工具数: {tool_count}",
        "",
    ]
    for i, step in enumerate(steps, start=1):
        kind = step.get("kind")
        is_tool = is_billable_action_step(step)
        title = (step.get("title") or step.get("name") or ("工具" if is_tool else "深度思考")).strip()
        name = (step.get("name") or "").strip()
        if name and name == title:
            name = title if is_tool else ""
        status = _format_step_status(step)
        raw_detail = strip_paths((step.get("detail") or "").strip())
        if kind == "thinking":
            detail = raw_detail
            inp = step.get("input") or ""
            result = step.get("result") or ""
            one_line = " ".join(detail.split()) if detail else " ".join(str(inp or result).split())
            if len(one_line) > 120:
                one_line = one_line[:117] + "…"
            inp = one_line
            result = one_line
        else:
            inp = strip_paths(sanitize_process_step_text((step.get("input") or "").strip()))
            result = sanitize_process_step_text(strip_paths((step.get("result") or "").strip()))
            detail = sanitize_process_step_text(strip_paths(raw_detail))
        if kind == "skill":
            type_label = "技能"
        elif kind == "web":
            type_label = "工具"
        elif kind == "tool":
            type_label = "工具"
        else:
            type_label = "思考"
        lines.append(f"### 步骤 {i} · {title}")
        lines.append(f"- 类型: {type_label}")
        lines.append(f"- 状态: {status}")
        lines.append(f"- 名称: {name or title}")
        lines.append(f"- 输入摘要: {inp}")
        lines.append(f"- 结果摘要: {result}")
        lines.append(f"- 详情: {detail}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def rebuild_reply_with_live_steps(
    raw_reply: str,
    live_steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    """Compose persisted reply: process section from steps + final from model stream."""
    steps = merge_live_steps(live_steps)
    if not steps:
        return raw_reply

    process_md = build_process_section_markdown(steps)
    model_final = extract_final_answer(raw_reply)
    final_body = resolve_final_answer(model_final, steps, skill_name)

    parts: list[str] = []
    if process_md.strip():
        parts.append(process_md.strip())
    if final_body.strip():
        parts.append("## 最终回答")
        parts.append("")
        parts.append(final_body.strip())
    return "\n".join(parts).strip() + "\n"
