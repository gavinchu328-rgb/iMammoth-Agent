"""Watch OpenClaw per-session JSONL logs for live tool/thinking events."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from config import settings
from text_sanitize import is_interm_status_only, sanitize_user_facing_text
from tool_summarize import friendly_tool_step, summarize_tool_result

OPENCLAW_SESSIONS_INDEX = Path(settings.openclaw_sessions_index)
OPENCLAW_SESSIONS_ROOT = Path(settings.openclaw_sessions_root)

# OpenClaw HTTP 流结束后，继续 tail 会话日志（子 Agent / 后续工具轮次）
POST_CONTENT_IDLE_ROUNDS = 25  # 0.2s * 25 ≈ 5s 无新日志后结束（短任务）
POST_CONTENT_IDLE_LONG_ROUNDS = 3000  # 0.2s * 3000 ≈ 10min（AI4Drug / 子代理等长任务）
POST_CONTENT_MAX_ROUNDS = 3000  # 0.2s * 3000 ≈ 10min 上限

_LONG_RUNNING_STEP_MARKERS = (
    "sessions_spawn",
    "分子设计",
    "molecule_design",
    "口袋预测",
    "pocket_prediction",
    "蛋白质获取",
    "protein_acquisition",
    "分子对接",
    "molecular_docking",
    "靶点发现",
    "target_discovery",
    "3d构象",
    "conformer_generation",
    "retrosynthesis",
    "逆合成",
    "molecule_evaluation",
    "admet",
    "后台进程",
)


def _step_is_long_tool_name(step: dict[str, Any]) -> bool:
    blob = f"{step.get('title', '')} {step.get('name', '')}".lower()
    return any(marker in blob for marker in _LONG_RUNNING_STEP_MARKERS)


def _step_indicates_long_running(step: dict[str, Any]) -> bool:
    """兼容旧逻辑：名称命中长任务标记，或正在 running。"""
    if str(step.get("status") or "").lower() == "running":
        return True
    return _step_is_long_tool_name(step)


def openclaw_session_key(mammoth_session_id: str, agent_id: str | None = None) -> str:
    """OpenClaw sessionKey：agent:<id>:openai-user:conv:<猛犸UUID>。"""
    agent = (agent_id or settings.openclaw_agent_id).strip() or "main"
    return f"agent:{agent}:openai-user:conv:{mammoth_session_id}"


def sessions_index_path(agent_id: str | None = None) -> Path:
    agent = (agent_id or settings.openclaw_agent_id).strip() or "main"
    return OPENCLAW_SESSIONS_ROOT / agent / "sessions" / "sessions.json"


def resolve_session_jsonl(
    mammoth_session_id: str,
    *,
    agent_id: str | None = None,
) -> Path | None:
    """查找 OpenClaw 会话 jsonl；优先指定 agent，再回退 sticky / main / ai4drug。"""
    from openclaw_route import load_sticky_agent

    candidates: list[str] = []
    if agent_id:
        candidates.append(agent_id.strip())
    sticky = load_sticky_agent(mammoth_session_id)
    if sticky and sticky not in candidates:
        candidates.append(sticky)
    for fallback in (settings.openclaw_agent_id, settings.openclaw_ai4drug_agent_id, "main"):
        if fallback and fallback not in candidates:
            candidates.append(fallback)

    for agent in candidates:
        index = sessions_index_path(agent)
        if not index.exists():
            continue
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entry = data.get(openclaw_session_key(mammoth_session_id, agent))
        if not entry:
            continue
        path = entry.get("sessionFile")
        if path:
            p = Path(path)
            if p.exists():
                return p
    return None


async def wait_for_session_jsonl(
    mammoth_session_id: str,
    *,
    timeout: float = 45.0,
    agent_id: str | None = None,
) -> Path | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        path = resolve_session_jsonl(mammoth_session_id, agent_id=agent_id)
        if path and path.exists():
            return path
        await asyncio.sleep(0.25)
    return None


def seed_seen_from_session_jsonl(path: Path) -> tuple[set[str], set[str]]:
    """Mark all existing OpenClaw records as seen so follow-up turns do not replay history."""
    seen_ids: set[str] = set()
    seen_content: set[str] = set()
    if not path.exists():
        return seen_ids, seen_content
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return seen_ids, seen_content
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid = record.get("id")
        if not rid:
            continue
        seen_ids.add(str(rid))
        if extract_assistant_text_from_record(record):
            seen_content.add(str(rid))
    return seen_ids, seen_content


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text") or "")
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(p for p in parts if p)
    return str(content or "")


def extract_assistant_text_from_record(record: dict[str, Any]) -> str:
    """从 jsonl 记录提取助手正文（过滤中间态占位）。"""
    if record.get("type") != "message":
        return ""
    msg = record.get("message") or {}
    if msg.get("role") != "assistant":
        return ""
    content = msg.get("content")
    if not isinstance(content, list):
        return sanitize_user_facing_text(_content_text(content))
    parts: list[str] = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = sanitize_user_facing_text((part.get("text") or "").strip())
        if text and not is_interm_status_only(text):
            parts.append(text)
    return "\n\n".join(parts)


def _extract_steps_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    if record.get("type") != "message":
        return []
    msg = record.get("message") or {}
    role = msg.get("role")
    content = msg.get("content")

    if role == "toolResult":
        raw = _content_text(content)
        tool_name = msg.get("toolName") or "tool"
        summarized = summarize_tool_result(tool_name, raw)
        friendly = friendly_tool_step(tool_name, {})
        status = "failed" if msg.get("isError") else "done"
        # mcporter/exec 后台启动：尚未真正结束，保持 running 以便前端继续等待
        low = (raw or "").lower()
        if (
            "timed out" in low
            or "appears offline" in low
            or "validation error" in low
            or "exec failed" in low
        ):
            status = "failed"
        elif (
            "command still running" in low
            or "process still running" in low
            or "(no new output)" in low
        ):
            status = "running"
        return [
            {
                "kind": friendly.get("kind") or "tool",
                "title": friendly["title"],
                "status": status,
                "name": friendly["name"],
                "input": "",
                "result": summarized["result"],
                "detail": summarized["detail"],
                "tool_call_id": msg.get("toolCallId"),
                "is_result_update": True,
            }
        ]

    if not isinstance(content, list):
        return []

    steps: list[dict[str, Any]] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        ptype = part.get("type")
        if ptype == "thinking":
            text = (part.get("thinking") or "").strip()
            if text:
                preview = text if len(text) <= 300 else text[:297] + "…"
                steps.append(
                    {
                        "kind": "thinking",
                        "title": "深度思考",
                        "status": "done",
                        "name": "深度思考",
                        "input": preview,
                        "result": preview,
                        "detail": text,
                    }
                )
        elif ptype == "toolCall":
            raw_name = part.get("name") or "tool"
            friendly = friendly_tool_step(raw_name, part.get("arguments"))
            steps.append(
                {
                    "kind": friendly.get("kind") or "tool",
                    "title": friendly["title"],
                    "status": "running",
                    "name": friendly["name"],
                    "input": friendly["input"],
                    "result": "",
                    "detail": "",
                    "tool_call_id": part.get("id"),
                }
            )
    return steps


def _read_jsonl_batch(path: Path, offset: int, *, allow_partial_last_line: bool) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records, offset
    try:
        with path.open("rb") as f:
            f.seek(offset)
            chunk = f.read()
            if not chunk:
                return records, offset
            text = chunk.decode("utf-8", errors="replace")
            if not text.endswith("\n") and not allow_partial_last_line:
                lines = text.splitlines()[:-1]
                consumed = sum(len(x.encode("utf-8")) + 1 for x in lines)
                new_offset = offset + consumed
            else:
                lines = text.splitlines()
                new_offset = f.tell()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            return records, new_offset
    except OSError:
        return records, offset


async def watch_session_jsonl(
    path: Path,
    *,
    seen_record_ids: set[str],
    content_ended: asyncio.Event,
    seen_content_ids: set[str],
    idle_long_rounds: int | None = None,
    max_rounds: int | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """Tail session jsonl. Yields ('step', step_dict) or ('content', text)."""
    offset = 0
    idle_rounds = 0
    rounds = 0
    running_long_ids: set[str] = set()
    idle_long_limit = idle_long_rounds if idle_long_rounds is not None else POST_CONTENT_IDLE_LONG_ROUNDS
    round_limit = max_rounds if max_rounds is not None else POST_CONTENT_MAX_ROUNDS

    while True:
        rounds += 1
        records, offset = _read_jsonl_batch(
            path,
            offset,
            allow_partial_last_line=content_ended.is_set(),
        )
        had_new = False
        for record in records:
            rid = record.get("id")
            if not rid:
                continue

            text = extract_assistant_text_from_record(record)
            if text and rid not in seen_content_ids:
                seen_content_ids.add(rid)
                had_new = True
                yield ("content", text)

            if rid in seen_record_ids:
                continue
            seen_record_ids.add(rid)
            steps = _extract_steps_from_record(record)
            if steps:
                had_new = True
            for step in steps:
                step["record_id"] = rid
                tid = str(step.get("tool_call_id") or "") or f"rec:{rid}:{step.get('name')}"
                status = str(step.get("status") or "").lower()
                result_blob = f"{step.get('result', '')} {step.get('detail', '')}".lower()
                still_bg = (
                    "command still running" in result_blob
                    or "process still running" in result_blob
                    or "命令仍在后台运行" in result_blob
                    or "后台任务仍在运行" in result_blob
                )
                if (status == "running" or still_bg) and (
                    _step_is_long_tool_name(step) or still_bg or step.get("name") in ("后台进程", "process")
                ):
                    running_long_ids.add(tid)
                    if still_bg:
                        step["status"] = "running"
                if status in ("done", "failed") and not still_bg:
                    running_long_ids.discard(tid)
                    if step.get("tool_call_id"):
                        running_long_ids.discard(str(step.get("tool_call_id")))
                    # process poll 取回结果后，清掉此前因 Command still running 挂起的长等待
                    name = str(step.get("name") or "")
                    inp = str(step.get("input") or "").lower()
                    if name in ("后台进程", "process") or "poll" in inp:
                        running_long_ids.clear()
                yield ("step", step)

        if had_new:
            idle_rounds = 0
        else:
            idle_rounds += 1

        if content_ended.is_set():
            # 仅当仍有长任务 running 时用长空闲；工具已完成后尽快结束
            idle_limit = idle_long_limit if running_long_ids else POST_CONTENT_IDLE_ROUNDS
            if idle_rounds >= idle_limit or rounds >= round_limit:
                break
        await asyncio.sleep(0.2)


def pick_best_assistant_reply(candidates: list[str]) -> str:
    """优先含「最终回答」的完整回复，否则取最长有效正文。"""
    cleaned = [sanitize_user_facing_text(c).strip() for c in candidates if c and c.strip()]
    if not cleaned:
        return ""
    for text in reversed(cleaned):
        if "## 最终回答" in text:
            return text
    return max(cleaned, key=len)
