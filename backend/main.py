import uuid
from datetime import datetime, timezone
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
from data_search import run_search
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
    selected_skill_name: str | None = None
    selected_skill_system_prompt: str | None = None


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


class DatabaseOut(BaseModel):
    id: str
    name: str
    category: str
    icon: str
    description: str
    volume: str
    source_type: str
    example_query: str
    searchable: bool
    project: str = "药物研发"


class DatabaseSearchRequest(BaseModel):
    query: str


class DatabaseSearchResponse(BaseModel):
    database_id: str
    query: str
    searchable: bool
    result: dict | None = None
    error: str | None = None
    message: str | None = None
    chat_prompt: str | None = None


# ── Helpers ──────────────────────────────────────────────

def _load_skills() -> list[SkillOut]:
    path = Path(__file__).parent / settings.skills_path
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [SkillOut(**s) for s in data["skills"]]


def _load_databases() -> list[DatabaseOut]:
    path = Path(__file__).parent / settings.databases_path
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    out: list[DatabaseOut] = []
    for raw in data["databases"]:
        raw = dict(raw)
        raw.setdefault("project", "药物研发")
        out.append(DatabaseOut(**raw))
    return out


def _load_process_log_spec() -> str:
    path = Path(__file__).parent / settings.process_log_spec_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def _openclaw_system_messages() -> list[dict]:
    msgs = [{"role": "system", "content": settings.openclaw_system_prompt}]
    spec = _load_process_log_spec()
    if spec:
        msgs.append(
            {
                "role": "system",
                "content": (
                    "以下是【过程日志输出规范】。你每次回复用户的最终 message content "
                    "必须严格遵守该规范（以「## 分析过程」开头，以「## 最终回答」收尾）：\n\n"
                    f"{spec}"
                ),
            }
        )
    return msgs


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


@app.get("/api/databases", response_model=list[DatabaseOut])
async def get_databases():
    return _load_databases()


@app.get("/api/databases/{database_id}", response_model=DatabaseOut)
async def get_database(database_id: str):
    for db in _load_databases():
        if db.id == database_id:
            return db
    raise HTTPException(404, "数据源不存在")


@app.post("/api/databases/{database_id}/search", response_model=DatabaseSearchResponse)
async def search_database(database_id: str, req: DatabaseSearchRequest):
    if not req.query.strip():
        raise HTTPException(400, "查询内容不能为空")
    meta = None
    for db in _load_databases():
        if db.id == database_id:
            meta = db
            break
    if not meta:
        raise HTTPException(404, "数据源不存在")

    out = run_search(database_id, req.query.strip())
    return DatabaseSearchResponse(
        database_id=database_id,
        query=req.query.strip(),
        searchable=bool(out.get("searchable")),
        result=out.get("result"),
        error=out.get("error"),
        message=out.get("message"),
        chat_prompt=out.get("chat_prompt"),
    )


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

    # OpenClaw 的 system 消息会影响技能匹配与工具选择。
    messages_for_openclaw = _openclaw_system_messages()

    if req.selected_skill_system_prompt:
        selected = (req.selected_skill_name or "").strip()
        messages_for_openclaw.append(
            {
                "role": "system",
                "content": (
                    f"用户已在猛犸前端选择了技能卡片：`{selected}`。\n"
                    f"{req.selected_skill_system_prompt.strip()}"
                ),
            }
        )

    messages_for_openclaw.extend(history)
    messages_for_openclaw.append({"role": "user", "content": req.message.strip()})

    try:
        reply, usage = await chat_completion(
            messages_for_openclaw,
            session_id=str(session.id),
        )
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

    session.updated_at = datetime.now(timezone.utc)

    if session.title == "新对话" or not history:
        session.title = _title_from_message(req.message)

    await db.commit()

    return ChatResponse(session_id=str(session.id), reply=reply, usage=usage)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.backend_port, reload=True)
