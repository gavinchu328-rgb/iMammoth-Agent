"""Shared chat session preparation for sync and streaming endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Message, Session


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


async def save_assistant_reply(
    *,
    session: Session,
    reply: str,
    user_message: str,
    had_history: bool,
) -> None:
    from database import async_session

    async with async_session() as db:
        result = await db.execute(select(Session).where(Session.id == session.id))
        s = result.scalar_one_or_none()
        if not s:
            return

        assistant_msg = Message(session_id=s.id, role="assistant", content=reply)
        db.add(assistant_msg)
        s.updated_at = datetime.now(timezone.utc)
        if s.title == "新对话" or not had_history:
            s.title = title_from_message(user_message)
        await db.commit()


async def stop_chat_session(
    *,
    session_id: uuid.UUID,
    reply: str,
    db: AsyncSession,
) -> str:
    """Mark process log done and persist a stopped assistant reply if awaiting one."""
    from process_log_store import append_process_done, read_process_log_snapshot
    from reply_rebuild import rebuild_reply_with_live_steps

    snap = read_process_log_snapshot(str(session_id))
    if snap.get("done"):
        return str(snap.get("reply") or reply or "（已停止生成）")

    steps = snap.get("steps") or []
    content = (reply or snap.get("content") or "").strip()
    if steps and content:
        final_reply = rebuild_reply_with_live_steps(content, steps)
    else:
        final_reply = content

    if not final_reply.strip():
        final_reply = "（已停止生成）"
    elif "（已停止生成）" not in final_reply:
        final_reply = f"{final_reply.rstrip()}\n\n（已停止生成）"

    append_process_done(str(session_id), reply=final_reply, steps=steps)

    result = await db.execute(
        select(Session)
        .options(selectinload(Session.messages))
        .where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "会话不存在")

    messages = list(session.messages or [])
    if messages and messages[-1].role == "user":
        user_text = messages[-1].content
        had_history = len(messages) > 1
        assistant_msg = Message(session_id=session.id, role="assistant", content=final_reply)
        db.add(assistant_msg)
        session.updated_at = datetime.now(timezone.utc)
        if session.title == "新对话" or not had_history:
            session.title = title_from_message(user_text)
        await db.commit()

    return final_reply
