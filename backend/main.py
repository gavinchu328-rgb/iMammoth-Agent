import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chat_helpers import prepare_chat_session, save_assistant_reply, title_from_message
from config import settings
from database import engine, get_db
from data_search import run_search
from models import Base, Message, Session
from openclaw_client import OpenClawError, chat_completion, chat_completion_stream, health_check
from openclaw_session_watch import wait_for_session_jsonl, watch_session_jsonl
from process_log_store import (
    PROCESS_LOG_DONE_TAG,
    PROCESS_LOG_DONE_TYPE,
    append_process_done,
    append_process_event,
    find_process_log,
    is_process_log_done,
    process_log_path,
)
from reply_rebuild import merge_live_steps, rebuild_reply_with_live_steps
from zh_normalize import normalize_step_zh

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
                    "必须严格遵守该规范（以「## 分析过程」开头，以「## 最终回答」收尾）。\n"
                    "另外：你的内部 thinking / 推理过程必须全程使用简体中文，"
                    "禁止出现 “The user wants...” 这类英文思考。\n\n"
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
    return title_from_message(text)


def _build_openclaw_messages(
    req: ChatRequest,
    history: list[dict],
) -> list[dict]:
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
    return messages_for_openclaw


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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

    session, history, _ = await prepare_chat_session(
        session_id=req.session_id,
        message=req.message,
        db=db,
    )

    messages_for_openclaw = _build_openclaw_messages(req, history)

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


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")

    session, history, _ = await prepare_chat_session(
        session_id=req.session_id,
        message=req.message,
        db=db,
    )
    session_id_str = str(session.id)
    messages_for_openclaw = _build_openclaw_messages(req, history)
    had_history = bool(history)

    async def event_generator():
        stop_event = asyncio.Event()
        seen_record_ids: set[str] = set()
        chunks: list[str] = []
        live_steps: list[dict] = []
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
        stream_error: str | None = None

        yield _sse("session", {"session_id": session_id_str})
        append_process_event(session_id_str, {"type": "session", "session_id": session_id_str})

        async def pump_content() -> None:
            nonlocal stream_error
            try:
                async for delta in chat_completion_stream(
                    messages_for_openclaw,
                    session_id=session_id_str,
                ):
                    chunks.append(delta)
                    append_process_event(session_id_str, {"type": "delta", "content": delta})
                    await queue.put(("delta", {"content": delta}))
            except OpenClawError as e:
                stream_error = str(e)
                await queue.put(("error", {"message": stream_error}))
            finally:
                stop_event.set()
                await queue.put(("_end", {}))

        async def pump_steps() -> None:
            path = await wait_for_session_jsonl(session_id_str)
            if not path:
                return
            async for step in watch_session_jsonl(
                path,
                seen_record_ids=seen_record_ids,
                stop_event=stop_event,
            ):
                step = await normalize_step_zh(step)
                append_process_event(session_id_str, {"type": "step", **step})
                await queue.put(("step", step))

        content_task = asyncio.create_task(pump_content())
        steps_task = asyncio.create_task(pump_steps())

        try:
            while True:
                kind, data = await queue.get()
                if kind == "_end":
                    break
                if kind == "step":
                    live_steps.append(data)
                yield _sse(kind, data)
        finally:
            stop_event.set()
            for task in (content_task, steps_task):
                task.cancel()
            await asyncio.gather(content_task, steps_task, return_exceptions=True)

        raw_reply = "".join(chunks)
        reply = (
            rebuild_reply_with_live_steps(raw_reply, live_steps)
            if live_steps and raw_reply and not stream_error
            else raw_reply
        )
        if reply and not stream_error:
            await save_assistant_reply(
                session=session,
                reply=reply,
                user_message=req.message,
                had_history=had_history,
            )

        done_payload = append_process_done(
            session_id_str,
            reply=reply,
            error=stream_error,
            steps=merge_live_steps(live_steps),
        )
        # SSE 同时发 mammoth_done（规范）与 done（兼容旧前端）
        yield _sse(PROCESS_LOG_DONE_TYPE, done_payload)
        yield _sse("done", done_payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions/{session_id}/process-log/stream")
async def stream_process_log(session_id: str):
    """Tail the per-session process log file and push new lines as SSE.

    读到结束标签 <<<MAMMOTH_DONE>>> / type=mammoth_done 后立刻关闭流。
    """

    async def tail_generator():
        # 读：按日期目录查找；文件尚未创建时等写入落到当天目录
        path = find_process_log(session_id)
        offset = 0
        idle_rounds = 0
        max_idle = 300  # ~60s without new data

        while idle_rounds < max_idle:
            if path is None or not path.exists():
                path = find_process_log(session_id) or process_log_path(session_id)
            if path.exists():
                try:
                    with path.open("rb") as f:
                        f.seek(offset)
                        chunk = f.read()
                        if chunk:
                            offset = f.tell()
                            idle_rounds = 0
                            for line in chunk.decode("utf-8", errors="replace").splitlines():
                                line = line.strip()
                                if not line:
                                    continue
                                # 纯文本结束标签
                                if line == PROCESS_LOG_DONE_TAG:
                                    yield _sse(
                                        PROCESS_LOG_DONE_TYPE,
                                        {
                                            "type": PROCESS_LOG_DONE_TYPE,
                                            "tag": PROCESS_LOG_DONE_TAG,
                                            "session_id": session_id,
                                        },
                                    )
                                    return
                                try:
                                    row = json.loads(line)
                                except json.JSONDecodeError:
                                    continue
                                # 旧日志里英文思考：读出时再译一次
                                if row.get("type") == "step" and row.get("kind") == "thinking":
                                    row = await normalize_step_zh(row)
                                event_type = row.get("type", "log")
                                yield _sse(event_type, row)
                                if is_process_log_done(row):
                                    return
                        else:
                            idle_rounds += 1
                except OSError:
                    idle_rounds += 1
            else:
                idle_rounds += 1
            await asyncio.sleep(0.2)

    return StreamingResponse(
        tail_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.backend_port, reload=True)
