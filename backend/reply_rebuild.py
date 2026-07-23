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
    return False


def step_merge_key(step: dict[str, Any]) -> str | None:
    tid = step.get("tool_call_id")
    if tid:
        return f"tid:{tid}"
    rid = step.get("record_id")
    kind = step.get("kind")
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


def _is_failed_step_result(result: str, detail: str = "") -> bool:
    blob = f"{result}\n{detail}".strip()
    if not blob:
        return True
    failures = (
        "接口调用失败",
        "命令执行失败",
        "命令未执行",
        "工作目录不可用",
        "执行失败",
        "搜索未完成",
        "PDB ID 应为",
        "RCSB 未找到数据",
        "未解析到分辨率",
        "分子设计失败",
        "未找到有效口袋",
        "Molecule design failed",
    )
    return any(token in blob for token in failures)


def _format_step_status(step: dict[str, Any]) -> str:
    st = str(step.get("status") or "done").lower()
    if st == "failed":
        return "失败"
    if st == "running":
        return "进行中"
    return "已执行"


def _parse_admet_metric_line(line: str) -> tuple[str, dict[str, str]] | None:
    line = line.strip()
    if not line:
        return None
    parts = [p.strip() for p in line.replace("|", "·").split("·") if p.strip()]
    if len(parts) < 2:
        return None
    mol_id = parts[0]
    metrics: dict[str, str] = {}
    for part in parts[1:]:
        tokens = part.split(None, 1)
        if len(tokens) == 2:
            metrics[tokens[0].strip()] = tokens[1].strip()
        elif part:
            metrics[part] = "—"
    return mol_id, metrics


def _format_admet_final_section(step: dict[str, Any]) -> str | None:
    title = (step.get("title") or step.get("name") or "").strip()
    name = (step.get("name") or "").lower()
    blob = f"{title} {name}".lower()
    if "admet" not in blob and "molecule_evaluation" not in blob and "评估" not in title:
        return None
    detail = (step.get("detail") or step.get("result") or "").strip()
    if not detail:
        return None
    rows: list[tuple[str, dict[str, str]]] = []
    for line in detail.splitlines():
        parsed = _parse_admet_metric_line(line)
        if parsed:
            rows.append(parsed)
    if not rows:
        parsed = _parse_admet_metric_line(detail.replace("\n", " · "))
        if parsed:
            rows.append(parsed)
    if not rows:
        return None
    metric_order: list[str] = []
    seen_metrics: set[str] = set()
    for _, metrics in rows:
        for key in metrics:
            if key not in seen_metrics:
                seen_metrics.add(key)
                metric_order.append(key)
    lines = [
        f"**{title or 'ADMET 评估结果'}**",
        "",
        "| 分子 ID | " + " | ".join(metric_order) + " |",
        "| --- | " + " | ".join("---" for _ in metric_order) + " |",
    ]
    for mol_id, metrics in rows:
        cells = [metrics.get(k, "—") for k in metric_order]
        lines.append(f"| {mol_id} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_pocket_final_section(step: dict[str, Any]) -> str | None:
    title = (step.get("title") or step.get("name") or "").strip()
    if "口袋" not in title and "pocket" not in title.lower():
        return None
    detail = (step.get("detail") or step.get("result") or "").strip()
    if not detail:
        return None
    rows: list[tuple[str, str, str]] = []
    for line in detail.splitlines():
        line = line.strip()
        if not line or "_pocket" not in line:
            continue
        parts = [p.strip() for p in line.split("·")]
        pid = parts[0] if parts else line
        score = ""
        prob = ""
        for part in parts[1:]:
            if "评分" in part:
                score = part.replace("评分", "").strip()
            elif "概率" in part:
                prob = part.replace("概率", "").strip()
        rows.append((pid, score, prob))
    if not rows:
        return None
    lines = [
        f"**{title or '口袋预测结果'}**",
        "",
        "| 口袋 ID | 评分 | 概率 |",
        "| --- | --- | --- |",
    ]
    for pid, score, prob in rows:
        lines.append(f"| {pid} | {score or '—'} | {prob or '—'} |")
    return "\n".join(lines)


def synthesize_final_from_steps(steps: list[dict[str, Any]]) -> str:
    """When the model omits ## 最终回答, build a readable summary from tool steps."""
    sections: list[str] = []
    seen_bodies: set[str] = set()
    for step in steps:
        kind = step.get("kind")
        if kind not in ("tool", "skill", "web"):
            continue
        pocket_block = _format_pocket_final_section(step)
        if pocket_block and pocket_block not in seen_bodies:
            seen_bodies.add(pocket_block)
            sections.append(pocket_block)
            continue
        admet_block = _format_admet_final_section(step)
        if admet_block and admet_block not in seen_bodies:
            seen_bodies.add(admet_block)
            sections.append(admet_block)
            continue
        title = (step.get("title") or step.get("name") or "工具").strip()
        result = (step.get("result") or "").strip()
        detail = (step.get("detail") or "").strip()
        if _is_failed_step_result(result, detail):
            continue
        if str(step.get("status") or "").lower() == "failed":
            continue
        body = detail or result
        if not body or body in seen_bodies:
            continue
        seen_bodies.add(body)
        sections.append(f"**{title}**\n\n{body}")
    return "\n\n".join(sections)


def rebuild_reply_with_live_steps(raw_reply: str, live_steps: list[dict[str, Any]]) -> str:
    """Prefer full live thinking/tool trail; keep model's final answer."""
    steps = merge_live_steps(live_steps)
    final = extract_final_answer(raw_reply)
    if not steps:
        return raw_reply

    tool_count = sum(1 for s in steps if s.get("kind") in ("tool", "skill", "web"))
    lines = [
        "## 分析过程",
        f"- 工具数: {tool_count}",
        "",
    ]
    for i, step in enumerate(steps, start=1):
        kind = step.get("kind")
        is_tool = kind in ("tool", "skill", "web")
        title = (step.get("title") or step.get("name") or ("工具" if is_tool else "深度思考")).strip()
        name = (step.get("name") or "").strip()
        if name and name == title:
            name = title if is_tool else ""
        status = _format_step_status(step)
        inp = strip_paths((step.get("input") or "").strip())
        result = strip_paths((step.get("result") or "").strip())
        detail = strip_paths((step.get("detail") or "").strip())
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

    lines.append("## 最终回答")
    lines.append("")
    if not final.strip() or _is_low_quality_final_answer(final):
        final = synthesize_final_from_steps(steps) or ""
    lines.append(final)
    return "\n".join(lines).strip() + "\n"
