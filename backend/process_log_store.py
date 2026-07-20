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
    """写入结束标记。监听方读到后必须停止。"""
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
    # 额外写一行纯文本标签，方便 grep / tail 脚本识别
    path = process_log_path(session_id)
    with path.open("a", encoding="utf-8") as f:
        f.write(PROCESS_LOG_DONE_TAG + "\n")
    return payload
