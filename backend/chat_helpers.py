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
