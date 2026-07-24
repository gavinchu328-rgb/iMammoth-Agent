"""Heal synthesized process-log snapshots and persist assistant replies."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from chat_helpers import persist_assistant_if_awaiting
from process_log_store import append_process_done, read_process_log_snapshot
from zh_normalize import normalize_steps_zh


async def prepare_process_log_snapshot(session_id: str, db: AsyncSession) -> dict:
    """Read snapshot, heal if needed (log file + DB), normalize step labels."""
    snap = read_process_log_snapshot(session_id)

    if snap.pop("needs_heal", False):
        healed_reply = str(snap.get("reply") or "").strip()
        if healed_reply:
            append_process_done(
                session_id,
                reply=healed_reply,
                steps=snap.get("steps") or [],
            )
            try:
                await persist_assistant_if_awaiting(
                    session_id=uuid.UUID(session_id),
                    reply=healed_reply,
                    db=db,
                )
            except ValueError:
                pass
        snap = read_process_log_snapshot(session_id)

    snap.pop("done_in_file", None)
    snap.pop("needs_heal", None)
    steps = snap.get("steps") or []
    if steps:
        snap["steps"] = await normalize_steps_zh(steps)
    return snap
