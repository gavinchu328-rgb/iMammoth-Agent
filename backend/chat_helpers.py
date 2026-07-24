"""Shared chat session preparation for sync and streaming endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Message, Session
from session_reply import (
    build_stopped_reply_from_snapshot,
    reply_from_done_snapshot,
)


def title_from_message(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return t[:40] + ("..." if len(t) > 40 else "")


async def prepare_chat_session(
    *,
    session_id: str | None,
    message: str,
    db: AsyncSession,
) -> tuple[Session, list[dict], bool]:
    """Create or load session, persist user message, return (session, history, is_new)."""
    text = message.strip()
    history: list[dict] = []
    is_new = False

    if session_id:
        result = await db.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == uuid.UUID(session_id))
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(404, "会话不存在")
        history = [{"role": m.role, "content": m.content} for m in session.messages]
    else:
        session = Session(title=title_from_message(text))
        db.add(session)
        await db.flush()
        is_new = True

    user_msg = Message(session_id=session.id, role="user", content=text)
    db.add(user_msg)

    await db.commit()
    await db.refresh(session)

    return session, history, is_new


async def _append_assistant_message(
    session: Session,
    *,
    reply: str,
    user_message: str,
    had_history: bool,
    db: AsyncSession,
) -> None:
    assistant_msg = Message(session_id=session.id, role="assistant", content=reply)
    db.add(assistant_msg)
    session.updated_at = datetime.now(timezone.utc)
    if session.title == "新对话" or not had_history:
        session.title = title_from_message(user_message)
    await db.commit()


async def save_assistant_reply(
    *,
    session: Session,
    reply: str,
    user_message: str,
    had_history: bool,
) -> None:
    from database import async_session

    text = (reply or "").strip()
    if not text:
        return

    async with async_session() as db:
        result = await db.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == session.id)
        )
        s = result.scalar_one_or_none()
        if not s:
            return

        messages = list(s.messages or [])
        if messages and messages[-1].role == "assistant":
            last = messages[-1]
            if last.content.strip() == text:
                return
            last.content = text
            s.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return

        await _append_assistant_message(
            s,
            reply=text,
            user_message=user_message,
            had_history=had_history,
            db=db,
        )


async def persist_assistant_if_awaiting(
    *,
    session_id: uuid.UUID,
    reply: str,
    db: AsyncSession,
) -> bool:
    """Persist assistant reply when the session still ends on a user message."""
    text = (reply or "").strip()
    if not text:
        return False

    result = await db.execute(
        select(Session)
        .options(selectinload(Session.messages))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return False

    messages = list(session.messages or [])
    if not messages or messages[-1].role != "user":
        return False

    user_text = messages[-1].content
    had_history = len(messages) > 1
    await _append_assistant_message(
        session,
        reply=text,
        user_message=user_text,
        had_history=had_history,
        db=db,
    )
    return True


async def _require_session(session_id: uuid.UUID, db: AsyncSession) -> None:
    exists = await db.execute(select(Session.id).where(Session.id == session_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(404, "会话不存在")


async def stop_chat_session(
    *,
    session_id: uuid.UUID,
    reply: str,
    db: AsyncSession,
) -> str:
    """Mark process log done and persist a stopped assistant reply if awaiting one."""
    from process_log_store import append_process_done, read_process_log_snapshot

    await _require_session(session_id, db)

    snap = read_process_log_snapshot(str(session_id))
    if snap.get("done"):
        final_reply = reply_from_done_snapshot(snap, reply)
    else:
        final_reply = build_stopped_reply_from_snapshot(snap, reply)
        append_process_done(str(session_id), reply=final_reply, steps=snap.get("steps") or [])

    await persist_assistant_if_awaiting(
        session_id=session_id,
        reply=final_reply,
        db=db,
    )
    return final_reply
