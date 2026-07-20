"""Watch OpenClaw per-session JSONL logs for live tool/thinking events."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

from config import settings
from tool_summarize import friendly_tool_step, summarize_tool_result

OPENCLAW_SESSIONS_INDEX = Path(settings.openclaw_sessions_index)


def openclaw_session_key(mammoth_session_id: str) -> str:
    return f"agent:main:openai-user:conv:{mammoth_session_id}"


def resolve_session_jsonl(mammoth_session_id: str) -> Path | None:
    if not OPENCLAW_SESSIONS_INDEX.exists():
        return None
    try:
        data = json.loads(OPENCLAW_SESSIONS_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entry = data.get(openclaw_session_key(mammoth_session_id))
    if not entry:
        return None
    path = entry.get("sessionFile")
    return Path(path) if path else None


async def wait_for_session_jsonl(mammoth_session_id: str, *, timeout: float = 45.0) -> Path | None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        path = resolve_session_jsonl(mammoth_session_id)
        if path and path.exists():
            return path
        await asyncio.sleep(0.25)
    return None


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


def _extract_steps_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    if record.get("type") != "message":
        return []
    msg = record.get("message") or {}
    role = msg.get("role")
    content = msg.get("content")

    # 工具结果：回填到对应 tool_call_id
    if role == "toolResult":
        raw = _content_text(content)
        tool_name = msg.get("toolName") or "tool"
        summarized = summarize_tool_result(tool_name, raw)
        return [
            {
                "kind": "tool",
                "title": tool_name,
                "status": "failed" if msg.get("isError") else "done",
                "name": tool_name,
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
                steps.append(
                    {
                        "kind": "thinking",
                        "title": "深度思考",
                        "status": "done",
                        "name": "深度思考",
                        "input": text[:120],
                        "result": text[:240],
                        "detail": text[:800],
                    }
                )
        elif ptype == "toolCall":
            raw_name = part.get("name") or "tool"
            friendly = friendly_tool_step(raw_name, part.get("arguments"))
            steps.append(
                {
                    "kind": "tool",
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


async def watch_session_jsonl(
    path: Path,
    *,
    seen_record_ids: set[str],
    stop_event: asyncio.Event,
) -> AsyncIterator[dict[str, Any]]:
    offset = 0
    # stop 后多扫几轮，避免漏掉紧随其后的 toolResult
    leftover_rounds = 0
    while not stop_event.is_set() or leftover_rounds < 8:
        if stop_event.is_set():
            leftover_rounds += 1
        if not path.exists():
            await asyncio.sleep(0.2)
            continue
        try:
            with path.open("rb") as f:
                f.seek(offset)
                chunk = f.read()
                if chunk:
                    # 若末尾不是换行，先不推进到文件尾，避免半行 JSON
                    text = chunk.decode("utf-8", errors="replace")
                    if not text.endswith("\n") and not stop_event.is_set():
                        # 等下一轮读完整行
                        lines = text.splitlines()[:-1]
                        consumed = sum(len(x.encode("utf-8")) + 1 for x in lines)
                        offset += consumed
                    else:
                        lines = text.splitlines()
                        offset = f.tell()
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        rid = record.get("id")
                        if not rid or rid in seen_record_ids:
                            continue
                        seen_record_ids.add(rid)
                        for step in _extract_steps_from_record(record):
                            step["record_id"] = rid
                            yield step
                elif stop_event.is_set():
                    pass
        except OSError:
            pass
        await asyncio.sleep(0.2)