"""Unified per-skill display formatters — single source of truth for UI markdown blocks.

Each AI4Drug skill has one formatter. Steps get ``display_block`` during polish;
frontend renders ``display_block`` directly (no duplicate parsing logic).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from tool_summarize import (
    is_billable_action_step,
    is_auxiliary_tool_step,
    is_process_display_noise,
    strip_process_runtime_noise,
)

StepFormatter = Callable[[dict[str, Any]], str | None]
SkillMatcher = Callable[[str], bool]


def _blob(step: dict[str, Any]) -> str:
    title = str(step.get("title") or "")
    name = str(step.get("name") or "")
    return f"{title} {name}".lower()


def _body(step: dict[str, Any]) -> str:
    if is_auxiliary_tool_step(step):
        return ""
    detail = strip_process_runtime_noise(str(step.get("detail") or ""))
    result = strip_process_runtime_noise(str(step.get("result") or ""))
    body = (detail or result).strip()
    if is_process_display_noise(body):
        return ""
    return body


def _heading(step: dict[str, Any], default: str) -> str:
    return (str(step.get("result") or step.get("title") or step.get("name") or default)).strip()


def _is_failed(step: dict[str, Any]) -> bool:
    blob = f"{step.get('result') or ''}\n{step.get('detail') or ''}".strip()
    if not blob:
        return True
    failures = (
        "接口调用失败",
        "命令执行失败",
        "执行失败",
        "分子设计失败",
        "未找到有效口袋",
        "Molecule design failed",
    )
    return any(t in blob for t in failures)


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


def _format_line_list(step: dict[str, Any], *, match: SkillMatcher, heading: str) -> str | None:
    if not match(_blob(step)):
        return None
    detail = _body(step)
    if not detail:
        return None
    lines = [ln.strip() for ln in detail.splitlines() if ln.strip()]
    if not lines:
        return None
    title = (step.get("title") or step.get("name") or heading).strip()
    body = "\n".join(f"- {ln}" for ln in lines)
    return f"**{title or heading}**\n\n{body}"


def format_ligand_preparation(step: dict[str, Any]) -> str | None:
    blob = _blob(step)
    if "配体" not in blob and "ligand" not in blob:
        return None
    detail = _body(step)
    if not detail:
        return None
    lines = [ln.strip() for ln in detail.splitlines() if ln.strip()]
    if not lines:
        return None
    title = str(step.get("result") or step.get("title") or "配体准备结果").strip()
    return f"**{title}**\n\n" + "\n".join(f"- {ln}" for ln in lines)


def format_retrosynthesis(step: dict[str, Any]) -> str | None:
    blob = _blob(step)
    if "逆合成" not in blob and "retrosynth" not in blob:
        return None
    detail = _body(step)
    result = strip_process_runtime_noise(str(step.get("result") or "").strip())
    if not detail and not result:
        return None
    title = result or str(step.get("title") or "逆合成分析结果").strip()
    lines = [ln.strip() for ln in (detail or result).splitlines() if ln.strip()]
    if not lines:
        if result:
            return f"**{title}**\n\n- {result}"
        return None
    body = "\n".join(f"- {ln}" if not ln.startswith("-") else ln for ln in lines)
    return f"**{title}**\n\n{body}"


def format_molecule_design(step: dict[str, Any]) -> str | None:
    blob = _blob(step)
    if "分子设计" not in blob and "molecule_design" not in blob:
        return None
    result = str(step.get("result") or "").strip()
    detail = str(step.get("detail") or "").strip()
    body = detail or result
    if not body:
        return None
    if body == result and "\n" not in body and "·" not in body and not re.search(r"\d+\.\s", body):
        return None
    lines: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = re.match(r"^\d+\.\s*(.+)", line)
        if m:
            lines.append(m.group(1).strip())
        elif "·" in line or line.startswith("|"):
            lines.append(line.lstrip("| ").strip())
    heading = result or str(step.get("title") or "分子设计结果")
    if lines:
        return f"**{heading}**\n\n" + "\n".join(f"- {ln}" for ln in lines)
    return f"**{heading}**\n\n{body}"


def format_pocket(step: dict[str, Any]) -> str | None:
    blob = _blob(step)
    if "口袋" not in blob and "pocket" not in blob:
        return None
    detail = _body(step)
    if not detail:
        return None
    rows: list[tuple[str, str, str]] = []
    for line in detail.splitlines():
        line = line.strip()
        if not line or "_pocket" not in line:
            continue
        if '"pocket_id":' in line or line.startswith("{") or line.startswith('"'):
            continue
        parts = [p.strip() for p in line.split("·")]
        pid = parts[0] if parts else line
        score = prob = ""
        for part in parts[1:]:
            if "评分" in part:
                score = part.replace("评分", "").strip()
            elif "概率" in part:
                prob = part.replace("概率", "").strip()
        rows.append((pid, score, prob))
    if not rows:
        return None
    title = str(step.get("title") or step.get("name") or "口袋预测结果")
    lines = [
        f"**{title}**",
        "",
        "| 口袋 ID | 评分 | 概率 |",
        "| --- | --- | --- |",
    ]
    for pid, score, prob in rows:
        lines.append(f"| {pid} | {score or '—'} | {prob or '—'} |")
    return "\n".join(lines)


def format_admet(step: dict[str, Any]) -> str | None:
    blob = _blob(step)
    title = str(step.get("title") or step.get("name") or "").strip()
    if "admet" not in blob and "molecule_evaluation" not in blob and "评估" not in title:
        return None
    detail = _body(step)
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
    seen: set[str] = set()
    for _, metrics in rows:
        for key in metrics:
            if key not in seen:
                seen.add(key)
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


def format_generic(step: dict[str, Any]) -> str | None:
    if str(step.get("kind") or "") == "thinking":
        return None
    if is_auxiliary_tool_step(step):
        return None
    if not is_billable_action_step(step):
        return None
    if _is_failed(step):
        return None
    if str(step.get("status") or "").lower() == "failed":
        return None
    detail = _body(step)
    if not detail:
        return None
    title = str(step.get("title") or step.get("name") or "结果").strip()
    if "\n" in detail:
        lines = [ln.strip() for ln in detail.splitlines() if ln.strip()]
        return f"**{title}**\n\n" + "\n".join(f"- {ln}" for ln in lines)
    return f"**{title}**\n\n{detail}"


# (skill matcher, formatter) — order matters: more specific first
SKILL_FORMATTERS: list[tuple[SkillMatcher, StepFormatter]] = [
    (lambda b: "分子设计" in b or "molecule_design" in b, format_molecule_design),
    (lambda b: "admet" in b or "molecule_evaluation" in b or "评估" in b, format_admet),
    (lambda b: ("口袋" in b or "pocket" in b) and "对接盒" not in b, format_pocket),
    (
        lambda b: "构象" in b or "conformer" in b,
        lambda s: _format_line_list(s, match=lambda x: "构象" in x or "conformer" in x, heading="3D 构象生成结果"),
    ),
    (
        lambda b: "配体" in b or "ligand" in b,
        format_ligand_preparation,
    ),
    (
        lambda b: "受体" in b or "receptor" in b,
        lambda s: _format_line_list(s, match=lambda x: "受体" in x or "receptor" in x, heading="受体准备结果"),
    ),
    (
        lambda b: "对接盒" in b or "docking_box" in b,
        lambda s: _format_line_list(s, match=lambda x: "对接盒" in x or "docking_box" in x, heading="对接盒配置结果"),
    ),
    (
        lambda b: ("分子对接" in b or "molecular_docking" in b or "对接" in b) and "对接盒" not in b,
        lambda s: _format_line_list(
            s,
            match=lambda x: ("分子对接" in x or "molecular_docking" in x or "对接" in x) and "对接盒" not in x,
            heading="分子对接结果",
        ),
    ),
    (
        lambda b: "靶点" in b or "target_discovery" in b,
        lambda s: _format_line_list(s, match=lambda x: "靶点" in x or "target" in x, heading="靶点发现结果"),
    ),
    (
        lambda b: "蛋白质" in b or "protein" in b,
        lambda s: _format_line_list(s, match=lambda x: "蛋白质" in x or "protein" in x, heading="蛋白质获取结果"),
    ),
    (
        lambda b: "逆合成" in b or "retrosynth" in b,
        format_retrosynthesis,
    ),
]


def format_step_display_block(step: dict[str, Any]) -> str | None:
    """Render one polished step → markdown block for the UI."""
    cached = str(step.get("display_block") or "").strip()
    if cached:
        return cached
    if str(step.get("kind") or "") == "thinking":
        return None
    if not is_billable_action_step(step):
        return None
    blob = _blob(step)
    for matcher, formatter in SKILL_FORMATTERS:
        if matcher(blob):
            block = formatter(step)
            if block:
                return block
    return format_generic(step)


def build_cumulative_display(steps: list[dict[str, Any]], *, only_done: bool = False) -> str:
    """Join per-step display blocks (in order, deduped)."""
    parts: list[str] = []
    seen: set[str] = set()
    for step in steps:
        if not is_billable_action_step(step):
            continue
        if only_done and str(step.get("status") or "").lower() not in ("done", "已完成"):
            continue
        if str(step.get("status") or "").lower() == "failed":
            continue
        block = format_step_display_block(step)
        if not block or block in seen:
            continue
        seen.add(block)
        parts.append(block)
    return "\n\n".join(parts)


_EARLY_SKILL_FORMATTERS: dict[str, tuple[StepFormatter, ...]] = {
    "分子设计": (format_molecule_design,),
    "口袋预测": (format_pocket,),
    "配体准备": (format_ligand_preparation,),
    "3D构象生成": (lambda s: _format_line_list(s, match=lambda x: "构象" in x or "conformer" in x, heading="3D 构象生成结果"),),
    "逆合成分析": (format_retrosynthesis,),
}

# 多步流水线技能：主工具完成后输出全部步骤摘要（而非仅最后一步）
_PIPELINE_FINAL_SKILLS: frozenset[str] = frozenset({"分子对接", "ADMET评估"})

_PRIMARY_SKILL_TOOL_NAMES: dict[str, frozenset[str]] = {
    "分子设计": frozenset({"分子设计"}),
    "口袋预测": frozenset({"口袋预测"}),
    "配体准备": frozenset({"配体准备"}),
    "3D构象生成": frozenset({"3D构象生成"}),
    "逆合成分析": frozenset({"逆合成分析"}),
    "ADMET评估": frozenset({"ADMET评估", "分子评估"}),
    "分子对接": frozenset({"分子对接"}),
    "对接盒配置": frozenset({"对接盒配置"}),
    "受体准备": frozenset({"受体准备"}),
    "靶点发现": frozenset({"靶点发现"}),
    "蛋白质获取": frozenset({"蛋白质获取"}),
}


def should_emit_early_final(steps: list[dict[str, Any]], skill_name: str | None = None) -> bool:
    """仅当主技能工具已成功完成时才注入 early final，避免多步流程中途误触发。"""
    skill = (skill_name or "").strip()
    if not skill:
        return False
    primary = _PRIMARY_SKILL_TOOL_NAMES.get(skill)
    if not primary:
        return False
    for step in steps:
        if str(step.get("kind") or "") != "tool":
            continue
        name = str(step.get("name") or step.get("title") or "")
        if name not in primary:
            continue
        if str(step.get("status") or "").lower() != "done":
            continue
        if _is_failed(step):
            continue
        return True
    return False


def synthesize_early_final_from_steps(
    steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    skill = (skill_name or "").strip()
    formatters = _EARLY_SKILL_FORMATTERS.get(
        skill,
        (
            format_molecule_design,
            format_pocket,
            format_ligand_preparation,
            format_retrosynthesis,
            lambda s: _format_line_list(s, match=lambda x: "构象" in x or "conformer" in x, heading="3D 构象生成结果"),
        ),
    )
    for step in reversed(steps):
        if not is_billable_action_step(step) or str(step.get("kind") or "") == "thinking":
            continue
        if str(step.get("status") or "").lower() != "done":
            continue
        for formatter in formatters:
            block = formatter(step)
            if block:
                return block
    return ""


def synthesize_final_from_steps(
    steps: list[dict[str, Any]],
    skill_name: str | None = None,
) -> str:
    """Join skill display blocks; skip synthesis until the primary tool finishes."""
    skill = (skill_name or "").strip()
    if skill and not should_emit_early_final(steps, skill):
        return ""
    if skill in _PIPELINE_FINAL_SKILLS:
        cumulative = build_cumulative_display(steps)
        if cumulative:
            return cumulative
    if skill in _EARLY_SKILL_FORMATTERS:
        block = synthesize_early_final_from_steps(steps, skill)
        if block:
            return block
    cumulative = build_cumulative_display(steps)
    if cumulative:
        return cumulative
    for step in reversed(steps):
        if not is_billable_action_step(step) or str(step.get("kind") or "") == "thinking":
            continue
        if str(step.get("status") or "").lower() == "failed":
            continue
        block = format_step_display_block(step)
        if block:
            return block
    return ""


def synthesize_pocket_final_from_steps(steps: list[dict[str, Any]]) -> str:
    for step in reversed(steps):
        if not is_billable_action_step(step) or str(step.get("kind") or "") == "thinking":
            continue
        block = format_pocket(step)
        if block:
            return block
    return ""
