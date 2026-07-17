import uuid
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import settings
from database import engine, get_db
from models import Base, Message, Session
from openclaw_client import OpenClawError, chat_completion, health_check

app = FastAPI(title="猛犸智能体 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────

class MessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: list[MessageOut] = []


class ChatResponse(BaseModel):
    session_id: str
    reply: str
    usage: dict | None = None


class SkillOut(BaseModel):
    id: str
    name: str
    category: str
    icon: str
    description: str
    example: str


# ── Helpers ──────────────────────────────────────────────

def _load_skills() -> list[SkillOut]:
    path = Path(__file__).parent / settings.skills_path
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [SkillOut(**s) for s in data["skills"]]


def _session_to_out(s: Session) -> SessionOut:
    return SessionOut(
        id=str(s.id),
        title=s.title,
        created_at=s.created_at.isoformat(),
        updated_at=s.updated_at.isoformat(),
        messages=[
            MessageOut(
                id=str(m.id),
                role=m.role,
                content=m.content,
                created_at=m.created_at.isoformat(),
            )
            for m in s.messages
        ],
    )


def _title_from_message(text: str) -> str:
    t = text.strip().replace("\n", " ")
    return t[:40] + ("..." if len(t) > 40 else "")


# ── Routes ───────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@app.get("/api/health")
async def api_health():
    ok = await health_check()
    return {"status": "ok" if ok else "degraded", "openclaw": ok, "database": True}


@app.get("/api/skills", response_model=list[SkillOut])
async def get_skills():
    return _load_skills()


@app.get("/api/sessions", response_model=list[SessionOut])
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).order_by(Session.updated_at.desc()).limit(50)
    )
    sessions = result.scalars().all()
    return [
        SessionOut(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at.isoformat(),
            updated_at=s.updated_at.isoformat(),
        )
        for s in sessions
    ]


@app.get("/api/sessions/{session_id}", response_model=SessionOut)
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .options(selectinload(Session.messages))
        .where(Session.id == uuid.UUID(session_id))
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "会话不存在")
    return _session_to_out(session)


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == uuid.UUID(session_id)))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(404, "会话不存在")
    await db.delete(session)
    await db.commit()
    return {"ok": True}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")

    history: list[dict] = []

    if req.session_id:
        result = await db.execute(
            select(Session)
            .options(selectinload(Session.messages))
            .where(Session.id == uuid.UUID(req.session_id))
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(404, "会话不存在")
        history = [{"role": m.role, "content": m.content} for m in session.messages]
    else:
        session = Session(title=_title_from_message(req.message))
        db.add(session)
        await db.flush()

    user_msg = Message(session_id=session.id, role="user", content=req.message.strip())
    db.add(user_msg)

    messages_for_openclaw = history + [{"role": "user", "content": req.message.strip()}]

    try:
        reply, usage = await chat_completion(messages_for_openclaw)
    except OpenClawError as e:
        raise HTTPException(502, str(e)) from e

    assistant_msg = Message(
        session_id=session.id,
        role="assistant",
        content=reply,
        prompt_tokens=usage.get("prompt_tokens") if usage else None,
        completion_tokens=usage.get("completion_tokens") if usage else None,
    )
    db.add(assistant_msg)

    if session.title == "新对话" or not history:
        session.title = _title_from_message(req.message)

    await db.commit()

    return ChatResponse(session_id=str(session.id), reply=reply, usage=usage)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.backend_port, reload=True)
