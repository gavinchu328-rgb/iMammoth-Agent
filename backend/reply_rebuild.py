"""Rebuild assistant process markdown from live OpenClaw steps."""

from __future__ import annotations

import re

from typing import Any

from tool_summarize import (
    _prefer_longer_text,
    is_billable_action_step,
    strip_paths,
    strip_process_runtime_noise,
)
from skill_display import (
    should_emit_early_final,
    synthesize_early_final_from_steps,
    synthesize_final_from_steps,
    synthesize_pocket_final_from_steps,
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
            return ""
        return raw

    def _clean_final_segment(text: str) -> str:
        proc = text.find("## 分析过程")
        proc2 = text.find("##分析过程")
        cut = -1
        for p in (proc, proc2):
            if p >= 0 and (cut < 0 or p < cut):
                cut = p
        if cut >= 0:
            text = text[:cut].strip()
        noise = text.find("\n⚠️")
        if noise >= 0:
            text = text[:noise].strip()
        return strip_process_runtime_noise(text).strip()

    candidates = [_clean_final_segment(raw[pos + mlen :]) for pos, mlen in positions]
    candidates = [c for c in candidates if c and not _is_low_quality_final_answer(c)]
    if candidates:
        return max(candidates, key=len)
    # fallback: last segment even if short
    last_pos, last_len = positions[-1]
    return _clean_final_segment(raw[last_pos + last_len :])


def _is_low_quality_final_answer(text: str) -> bool:
    """Detect collapsed process templates the model sometimes dumps as final answer."""
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
            "状态:进行中",
            "状态:等待",
            "-状态:进行中",
            "-状态:等待",
        )
    ):
        return True
    # Status-only lines without real tool output (e.g. "✅步骤1…✅步骤2…")
    if t.count("✅") >= 2 and not any(
        marker in t for marker in ("QED", "评分", "pocket", "PDB", "|", "对接", "hERG", "BBB")
    ):
        return True
    if '"pocket_id":' in t or '"molecules":' in t:
        return True
    if re.search(r'"\w+"\s*:\s*"', t) and "|" in t:
        return True
    return False


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


def _is_brief_model_summary(model: str, structured: str) -> bool:
    m = (model or "").strip()
    s = (structured or "").strip()
    if not s:
        return False
    if not m or _is_low_quality_final_answer(m):
        return True
    if "|" in s and "|" not in m:
        return True
    if s.count("\n") >= 3 and m.count("\n") < 2:
        return True
    if len(s) > len(m) + 80:
        return True
    return False


def _is_truncated_final_answer(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.endswith(("：", ":", "，", ",", "、", "|", "—", "-", "…")):
        return True
    if re.search(r"\*\*[^*]+\*\*\s*$", t):
        return True
    if t.count("##") > 0 and len(t) < 200:
        return True
    return False


def _merge_final_answer(
    model_final: str,
    steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    """Merge tool-structured output with model prose; never drop the richer block."""
    final = strip_process_runtime_noise((model_final or "").strip())
    synthesized = ""
    if not skill_name or should_emit_early_final(steps, skill_name):
        synthesized = (synthesize_final_from_steps(steps, skill_name) or "").strip()
    if not synthesized:
        return final
    if not final or _is_low_quality_final_answer(final):
        return synthesized
    if synthesized in final:
        return final
    if final in synthesized:
        return synthesized
    if _is_truncated_final_answer(final) and not _is_truncated_final_answer(synthesized):
        return synthesized
    if _is_brief_model_summary(final, synthesized):
        return synthesized
    if len(synthesized) > len(final) + 120 and _is_truncated_final_answer(final):
        return synthesized
    return f"{synthesized}\n\n{final}"


def rebuild_reply_with_live_steps(
    raw_reply: str,
    live_steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    """Prefer full live thinking/tool trail; keep model's final answer."""
    steps = merge_live_steps(live_steps)
    final = extract_final_answer(raw_reply)
    if not steps:
        return raw_reply

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
        inp = strip_paths((step.get("input") or "").strip())
        result = strip_process_runtime_noise(strip_paths((step.get("result") or "").strip()))
        detail = strip_process_runtime_noise(strip_paths((step.get("detail") or "").strip()))
        if kind == "thinking" and detail:
            inp = detail[:300] + ("…" if len(detail) > 300 else "")
            result = inp
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

    merged_final = _merge_final_answer(final, steps, skill_name)
    if merged_final.strip():
        lines.append("## 最终回答")
        lines.append("")
        lines.append(merged_final)
    return "\n".join(lines).strip() + "\n"
