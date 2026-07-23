"""Append structured process events to per-session log files.

协议约定（监听方必须遵守）：
- 日志目录：/data2/mammoth-agent/process_logs/{YYYY-MM-DD}/{session_id}.jsonl
- 每行一个 JSON 对象
- 结束标记：type == "mammoth_done" 且 tag == "<<<MAMMOTH_DONE>>>"
- 见到该行必须立刻停止 tail / 停止轮询，不得继续询问结果
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings

# ── 结束标签（前后端 / 脚本统一约定）──────────────────────
PROCESS_LOG_DONE_TYPE = "mammoth_done"
PROCESS_LOG_DONE_TAG = "<<<MAMMOTH_DONE>>>"


def process_log_root() -> Path:
    configured = Path(settings.process_log_dir)
    root = configured if configured.is_absolute() else Path(__file__).parent / configured
    root.mkdir(parents=True, exist_ok=True)
    return root


def process_log_day_dir(day: str | None = None) -> Path:
    """按本地日期分子目录，如 2026-07-20。"""
    day = day or datetime.now().strftime("%Y-%m-%d")
    path = process_log_root() / day
    path.mkdir(parents=True, exist_ok=True)
    return path


def process_log_path(session_id: str) -> Path:
    """写入路径：始终落到当天目录。"""
    return process_log_day_dir() / f"{session_id}.jsonl"


def find_process_log(session_id: str) -> Path | None:
    """读取时查找：当天 → 各日期目录 → 根目录旧文件。"""
    name = f"{session_id}.jsonl"
    root = process_log_root()
    candidates = [
        process_log_day_dir() / name,
        root / name,
    ]
    # 日期目录按名称倒序（新的优先）
    day_dirs = sorted(
        (p for p in root.iterdir() if p.is_dir() and len(p.name) == 10),
        key=lambda p: p.name,
        reverse=True,
    )
    for d in day_dirs:
        candidates.append(d / name)
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            return path
    return None


def is_process_log_done(row: dict[str, Any] | str) -> bool:
    """判断是否为「本轮日志已结束」标记。见到即应停止监听。"""
    if isinstance(row, str):
        text = row.strip()
        if text == PROCESS_LOG_DONE_TAG:
            return True
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            return PROCESS_LOG_DONE_TAG in text
    if not isinstance(row, dict):
        return False
    return (
        row.get("type") == PROCESS_LOG_DONE_TYPE
        or row.get("tag") == PROCESS_LOG_DONE_TAG
        # 兼容旧日志
        or row.get("type") == "done"
    )


def _content_reply_ready(content: str) -> bool:
    idx = content.find("## 最终回答")
    if idx < 0:
        return False
    return len(content[idx + len("## 最终回答") :].strip()) >= 8


def _synthesize_reply_from_content(content: str) -> str:
    text = (content or "").strip()
    proc_idx = text.rfind("## 分析过程")
    final_idx = text.rfind("## 最终回答")
    if proc_idx >= 0 and final_idx > proc_idx:
        return text[proc_idx:].strip()
    from reply_rebuild import extract_final_answer

    final = extract_final_answer(text)
    return final or text


def _file_has_done_marker(session_id: str) -> bool:
    path = find_process_log(session_id)
    if not path or not path.exists():
        return False
    try:
        tail = path.read_text(encoding="utf-8", errors="replace")[-8192:]
    except OSError:
        return False
    if PROCESS_LOG_DONE_TAG in tail:
        return True
    return '"type": "mammoth_done"' in tail or f'"type": "{PROCESS_LOG_DONE_TYPE}"' in tail


def read_process_log_snapshot(session_id: str) -> dict[str, Any]:
    """读取过程日志快照，供刷新页面后恢复进行中的分析过程。"""
    path = find_process_log(session_id)
    empty: dict[str, Any] = {
        "in_progress": False,
        "done": False,
        "content": "",
        "steps": [],
        "reply": "",
        "error": None,
        "log_offset": 0,
    }
    if not path or not path.exists():
        return empty

    content_parts: list[str] = []
    raw_steps: list[dict[str, Any]] = []
    done_payload: dict[str, Any] | None = None
    stream_budget_sec: float | None = None
    molecule_count: int | None = None
    sealed_turns: list[dict[str, Any]] = []

    def _seal_turn() -> None:
        nonlocal content_parts, raw_steps, done_payload
        if content_parts or raw_steps or done_payload:
            sealed_turns.append(
                {
                    "content_parts": content_parts,
                    "raw_steps": raw_steps,
                    "done_payload": done_payload,
                }
            )
        content_parts = []
        raw_steps = []
        done_payload = None

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line == PROCESS_LOG_DONE_TAG:
            if content_parts or raw_steps:
                done_payload = done_payload or {
                    "type": PROCESS_LOG_DONE_TYPE,
                    "tag": PROCESS_LOG_DONE_TAG,
                    "session_id": session_id,
                }
                _seal_turn()
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if is_process_log_done(row):
            done_payload = row
            _seal_turn()
            continue
        event_type = row.get("type")
        if event_type == "session":
            if row.get("stream_budget_sec") is not None:
                stream_budget_sec = float(row["stream_budget_sec"])
            if row.get("molecule_count") is not None:
                molecule_count = int(row["molecule_count"])
        elif event_type == "delta":
            part = row.get("content")
            if part:
                content_parts.append(str(part))
        elif event_type == "step":
            raw_steps.append({k: v for k, v in row.items() if k not in ("type", "ts")})

    if content_parts or raw_steps:
        active_turn = {
            "content_parts": content_parts,
            "raw_steps": raw_steps,
            "done_payload": done_payload,
        }
    elif sealed_turns:
        active_turn = next(
            (t for t in reversed(sealed_turns) if t["content_parts"] or t["raw_steps"]),
            sealed_turns[-1],
        )
    else:
        active_turn = {"content_parts": [], "raw_steps": [], "done_payload": None}

    content_parts = active_turn["content_parts"]
    raw_steps = active_turn["raw_steps"]
    done_payload = active_turn["done_payload"]

    from reply_rebuild import merge_live_steps
    from tool_summarize import polish_ai4drug_exec_steps

    log_offset = path.stat().st_size
    has_activity = bool(content_parts or raw_steps)
    content = "".join(content_parts)
    merged_steps = polish_ai4drug_exec_steps(merge_live_steps(raw_steps))
    done_in_file = done_payload is not None
    running = any(str(s.get("status") or "").lower() == "running" for s in merged_steps)
    synthesized = (
        not done_in_file
        and bool(content)
        and _content_reply_ready(content)
        and not running
    )
    complete = done_in_file or synthesized
    reply = str((done_payload or {}).get("reply") or "")
    if synthesized and not reply:
        reply = _synthesize_reply_from_content(content)

    return {
        "in_progress": has_activity and not complete,
        "done": complete,
        "done_in_file": done_in_file,
        "needs_heal": synthesized,
        "content": content,
        "steps": merged_steps,
        "reply": reply,
        "error": (done_payload or {}).get("error"),
        "log_offset": log_offset,
        "stream_budget_sec": stream_budget_sec,
        "molecule_count": molecule_count,
    }


def append_process_event(session_id: str, event: dict) -> None:
    path = process_log_path(session_id)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_process_done(
    session_id: str,
    *,
    reply: str = "",
    error: str | None = None,
    **extra: Any,
) -> dict:
    """写入结束标记。监听方读到后必须停止。多轮对话每轮各写一次。"""
    payload = {
        "type": PROCESS_LOG_DONE_TYPE,
        "tag": PROCESS_LOG_DONE_TAG,
        "session_id": session_id,
        "reply": reply,
        "error": error,
        "ok": error is None,
        **extra,
    }
    append_process_event(session_id, payload)
    path = process_log_path(session_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(PROCESS_LOG_DONE_TAG + "\n")
    return payload
