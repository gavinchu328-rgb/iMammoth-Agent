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
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from chat_helpers import prepare_chat_session, save_assistant_reply, stop_chat_session, title_from_message
from process_log_heal import prepare_process_log_snapshot
from config import settings
from database import engine, get_db
from data_search import run_search
from models import Base, Message, Session
from openclaw_client import OpenClawError, chat_completion, chat_completion_stream, ping_openclaw
from openclaw_route import resolve_openclaw_route
from openclaw_session_watch import (
    pick_best_assistant_reply,
    wait_for_session_jsonl,
    watch_session_jsonl,
)
from process_log_store import (
    PROCESS_LOG_DONE_TAG,
    PROCESS_LOG_DONE_TYPE,
    append_process_done,
    append_process_event,
    find_process_log,
    is_process_log_done,
    process_log_path,
    read_process_log_snapshot,
)
from reply_rebuild import merge_live_steps, rebuild_reply_with_live_steps
from stream_content_filter import ClientStreamFilter
from stream_timeouts import budget_from_process_log, estimate_stream_budget
from text_sanitize import is_interm_status_only, sanitize_user_facing_text
from zh_normalize import normalize_step_zh, normalize_steps_zh

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
    selected_skill_category: str | None = None


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
    categories: list[str] = []
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
    storage_path: str | None = None
    service_endpoint: str | None = None


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


class ProcessLogSnapshotOut(BaseModel):
    in_progress: bool
    done: bool
    content: str = ""
    steps: list[dict] = []
    reply: str = ""
    error: str | None = None
    log_offset: int = 0
    stream_budget_sec: float | None = None
    molecule_count: int | None = None


class StopSessionRequest(BaseModel):
    reply: str | None = None


# ── Helpers ──────────────────────────────────────────────

def _normalize_skill(raw: dict) -> SkillOut:
    """Support single category or multiple category tags per skill."""
    categories_raw = raw.get("categories")
    if isinstance(categories_raw, list):
        categories = [str(c).strip() for c in categories_raw if str(c).strip()]
    else:
        categories = []
    if not categories:
        primary = str(raw.get("category") or "").strip()
        categories = [primary] if primary else []
    primary_category = categories[0] if categories else str(raw.get("category") or "")
    return SkillOut(
        id=str(raw["id"]),
        name=str(raw["name"]),
        category=primary_category,
        categories=categories,
        icon=str(raw.get("icon") or ""),
        description=str(raw.get("description") or ""),
        example=str(raw.get("example") or ""),
    )


def _load_skills() -> list[SkillOut]:
    path = Path(__file__).parent / settings.skills_path
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [_normalize_skill(s) for s in data["skills"]]


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
                    "禁止出现 “The user wants...” 这类英文思考。\n"
                    "对用户展示时一律称「猛犸智能体」，禁止出现 OpenClaw Agent 字样；"
                    "禁止输出「正在通过 OpenClaw Agent 处理您的请求」等中间占位语，"
                    "也不要使用 sessions_spawn 子 Agent；应直接调用 MCP 工具完成任务。\n\n"
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
    *,
    mammoth_session_id: str | None = None,
) -> list[dict]:
    messages_for_openclaw = _openclaw_system_messages()

    if mammoth_session_id:
        mcp_to = settings.mcp_tool_timeout_ms
        messages_for_openclaw.append(
            {
                "role": "system",
                "content": (
                    f"当前猛犸对话会话 ID：`{mammoth_session_id}`。\n"
                    f"OpenClaw 请求已用 user=`conv:{mammoth_session_id}` 绑定同一服务端会话；"
                    "禁止 sessions_spawn 开新对话，否则工具上下文会丢失。\n"
                    "调用 ai4drug MCP 工具时，必须把 session_id 参数设为该 UUID 字符串，禁止传 null。\n"
                    f"通过 exec 调用 mcporter 时，所有 ai4drug 工具必须显式加 --timeout {mcp_to}（毫秒，即 10 分钟；勿写成 600）。\n"
                    "含 conformer_generation、ligand_preparation、molecular_docking、pocket_prediction 等；"
                    "conformer_generation 不传 session_id 会创建孤立数据会话，导致口袋预测/对接失败。\n"
                    "protein_acquisition / receptor_preparation / pocket_prediction 的 target_ids "
                    "必须使用 `基因符号_PDBID` 格式（例如 EGFR_3W2S），不能仅传基因符号。\n"
                    "molecular_docking 的 molecule_ids 必须为 `{pocket_id}_mol0`（如 EGFR_3W2S_pocket1_mol0），"
                    "且须先用 conformer_generation 以相同 id 写入同一 session。"
                ),
            }
        )

    if req.selected_skill_system_prompt:
        selected = (req.selected_skill_name or "").strip()
        mcp_to = settings.mcp_tool_timeout_ms
        extra = ""
        if selected == "配体准备":
            extra = (
                "\n配体准备本技能仅输出 PDBQT 配体文件，标准流程只有两步（禁止扩展为完整对接流水线）：\n"
                f"1) conformer_generation：session_id 必须为当前猛犸 UUID（禁止用 target_discovery 返回的 session_id）；"
                "molecules=[{id: `{pocket_id}_mol0`, smiles: ...}]\n"
                "2) ligand_preparation：molecule_ids 与构象 id 完全一致\n"
                "用户已给出 SMILES 与 pocket_id / molecule id（如 EGFR_3W2S_pocket1_mol0）时："
                "只执行上述两步；禁止靶点发现、禁止 web_search 查 SMILES、"
                "禁止 protein_acquisition / pocket_prediction（除非用户明确说 session 里还没有口袋）。\n"
                "禁止受体准备、对接盒配置、分子对接；「对接配体」仅指生成 PDBQT，不是执行对接。\n"
                "用户只给药物名时：吉非替尼 SMILES 用 CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl；"
                "未给 pocket 时默认 EGFR_3W2S_pocket1_mol0，若 session 无口袋才补 protein_acquisition + pocket_prediction。\n"
                f"所有 mcporter 调用必须加 --timeout {mcp_to}；禁止 sessions_spawn。"
            )
        elif selected == "靶点发现":
            extra = (
                f"\n靶点发现：通过 exec 调用 mcporter call ai4drug.target_discovery，"
                f"必须显式加 --timeout {mcp_to}（毫秒，10 分钟）。"
                "传入 disease_name 与当前猛犸 session_id；禁止 sessions_spawn、禁止后台 process 轮询。"
                "一次调用同步等待返回即可。"
            )
        elif selected == "分子设计":
            extra = (
                "\n分子设计正确流程：\n"
                f"1) 若 session 尚无口袋：protein_acquisition（target_ids 如 EGFR_3W2S）+ pocket_prediction；"
                f"所有 mcporter 调用必须加 --timeout {mcp_to}；\n"
                "2) molecule_design 的 pocket_ids 必须用 pocket_prediction 返回的完整 pocket_id"
                "（如 EGFR_3W2S_pocket1），禁止只传 pocket1；\n"
                "3) num_to_generate=用户要求数量（3~8），只调用一次 molecule_design；\n"
                "4) 必须同步等待 mcporter/MCP 返回完整 JSON（含 molecules[]），"
                "禁止后台 process 轮询、禁止 sessions_spawn。\n"
                "用户已指定 EGFR/口袋时禁止靶点发现；禁止受体准备、对接、ADMET。"
            )
        elif selected == "对接盒配置":
            extra = (
                "\n对接盒配置本技能仅输出对接搜索盒参数，禁止受体准备、配体准备、分子对接、靶点发现。\n"
                f"全程 session_id 必须为当前猛犸 UUID；所有 mcporter 加 --timeout {mcp_to}。\n"
                "pocket_ids 必须用完整 pocket_id（如 EGFR_3W2S_pocket1），从用户问题中的 pocket_id 推断 target_id（如 EGFR_3W2S）。\n"
                "用户文本里写了 pocket_id ≠ session 磁盘上已有口袋；新会话/本对话尚未执行过 pocket_prediction 时：\n"
                "  先 protein_acquisition(target_ids=[推断的 target_id]) → pocket_prediction → docking_box_config；\n"
                "  不要先单独调 docking_box_config 等报「尚无口袋」再补步骤。\n"
                "禁止 sessions_spawn；禁止 web_search；用户已给 EGFR/3W2S/pocket_id 时禁止追问 PDB。"
            )
        elif selected == "分子对接":
            extra = (
                "\n分子对接正确流程（全程同一猛犸 session_id，禁止 sessions_spawn）：\n"
                "1) protein_acquisition：target_ids 如 [\"EGFR_3W2S\"]；\n"
                "2) receptor_preparation：target_ids 同上；\n"
                "3) pocket_prediction → 取最高分 pocket_id（如 EGFR_3W2S_pocket1）；\n"
                "4) docking_box_config：pocket_ids 用完整 pocket_id；\n"
                "5) conformer_generation：molecules 每项 id 必须为 `{pocket_id}_mol0`"
                "（如 EGFR_3W2S_pocket1_mol0），smiles 为配体 SMILES，必须传猛犸 session_id；\n"
                "6) ligand_preparation：molecule_ids 与上一步 id 完全一致；\n"
                "7) molecular_docking：molecule_ids 同上；禁止用 gefitinib/药物名 作为 molecule_id。\n"
                "吉非替尼 SMILES：CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl。\n"
                "用户已给 EGFR/PDB/药物名时禁止靶点发现；禁止在未对接成功前调用 pipeline_summary。"
            )
        elif selected == "受体准备":
            extra = (
                "\n受体准备：先 protein_acquisition（target_ids 如 EGFR_3W2S），"
                "再 receptor_preparation（target_ids 同上，session_id 为猛犸 UUID）。"
                "禁止 sessions_spawn。"
            )
        elif selected == "3D构象生成":
            extra = (
                "\n3D构象生成：必须调用 ai4drug__conformer_generation，"
                "session_id 必须为猛犸 UUID（禁止省略，禁止自造时间戳 session），"
                "molecules[].id 可用简短 id（如 aspirin）。禁止 sessions_spawn。"
            )
        elif selected == "ADMET评估":
            extra = (
                "\nADMET 评估本技能仅两步：conformer_generation → molecule_evaluation；禁止靶点发现、对接、联网查 SMILES。\n"
                f"全程 session_id 必须为当前猛犸 UUID；mcporter 加 --timeout {mcp_to}。\n"
                "用户已给 SMILES 时：禁止 web_search / web_fetch / tavily；直接用给定 SMILES，不要自行编造或上网核对。\n"
                "用户只给药物名时：吉非替尼 SMILES 用 CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl，id=gefitinib_mol0。\n"
                "conformer_generation：molecules=[{id, smiles}]；多分子时用 mcporter --args-file 传 JSON，不要 shell 内嵌长 JSON。\n"
                "molecule_evaluation：molecule_ids 与构象 id 完全一致。禁止 sessions_spawn。"
            )
        elif selected == "逆合成分析":
            extra = (
                "\n逆合成分析正确流程：\n"
                "1) conformer_generation：传猛犸 session_id，molecules=[{id: gefitinib_mol0, smiles: ...}]；\n"
                "2) retrosynthesis：molecule_ids=[gefitinib_mol0]，同一 session_id；\n"
                "禁止 sessions_spawn；禁止用后台 process 轮询代替工具返回；等工具完整返回后再总结。"
            )
        elif selected == "口袋预测":
            extra = (
                "\n口袋预测正确流程：\n"
                f"1) protein_acquisition（target_ids 如 [\"EGFR_3W2S\"]）必须加 mcporter --timeout {mcp_to}；\n"
                f"2) pocket_prediction（target_ids 同上，session_id 为猛犸 UUID）必须加 --timeout {mcp_to}；\n"
                "禁止 sessions_spawn。最终回答必须用表格列出 pocket_id、评分、概率（按评分降序）。"
            )
        elif selected == "蛋白质获取":
            extra = (
                f"\n蛋白质获取：mcporter call ai4drug.protein_acquisition 必须加 --timeout {mcp_to}，"
                "target_ids 格式基因_PDB（如 EGFR_3W2S），传猛犸 session_id。禁止 sessions_spawn。"
            )
        elif selected == "PDB 文本搜索":
            extra = (
                "\n禁止 read database-lookup、禁止 sessions_spawn、禁止凭记忆编造 PDB 结果。"
                "\n禁止 curl data.rcsb.org、search.rcsb.org 或手写 RCSB 脚本。"
                "\n必须 exec 一次：curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb-text/search "
                "-H 'Content-Type: application/json' -d '{\"query\":\"<关键词>\"}'"
                "\n结果已按分辨率从高到低排序；解析 total_count 与 hits[].pdb_id、hits[].resolution，"
                "直接列出前 10 条即可回答「高分辨率」问题；步骤名写「PDB 文本搜索」。"
            )
        elif selected == "PDB 元数据查询":
            extra = (
                "\n禁止 read database-lookup、禁止 sessions_spawn。"
                "\n禁止 curl data.rcsb.org、search.rcsb.org；query 必须是 4 位 PDB ID，不要用 entity id。"
                "\n必须 exec 一次：curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb-metadata/search "
                "-H 'Content-Type: application/json' -d '{\"query\":\"<PDB_ID>\"}'"
                "\n解析 resolution、experimental_method、title、release_date、ligands[]；"
                "禁止为配体 entity 再调接口；步骤名写「PDB 元数据查询」。"
            )
        elif selected == "PDB 结构下载":
            extra = (
                "\n禁止 read database-lookup、禁止 sessions_spawn。"
                "\n必须 exec 一次：curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb/search "
                "-H 'Content-Type: application/json' -d '{\"query\":\"<PDB_ID>\"}'"
                "\n给出 download_url、reachable；步骤名写「PDB 结构下载」。"
                "\n3D 预览链接：https://www.rcsb.org/3d-view/<PDB_ID>。"
            )
        messages_for_openclaw.append(
            {
                "role": "system",
                "content": (
                    f"用户已在猛犸前端选择了技能卡片：`{selected}`。\n"
                    f"{req.selected_skill_system_prompt.strip()}{extra}"
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


async def _db_ping() -> bool:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@app.get("/api/health")
async def api_health():
    """Fast liveness probe: backend + database only (no OpenClaw LLM call)."""
    db_ok = await _db_ping()
    return {
        "status": "ok" if db_ok else "degraded",
        "backend": True,
        "database": db_ok,
    }


@app.get("/api/health/deep")
async def api_health_deep():
    """Dependency probe for ops scripts (OpenClaw gateway, DB)."""
    db_ok, openclaw_ok = await asyncio.gather(_db_ping(), ping_openclaw())
    ok = db_ok and openclaw_ok
    return {
        "status": "ok" if ok else "degraded",
        "backend": True,
        "database": db_ok,
        "openclaw": openclaw_ok,
    }


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


@app.post("/api/sessions/{session_id}/stop")
async def stop_session(
    session_id: str,
    req: StopSessionRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    """用户主动停止生成：写入过程日志结束标记并保存已生成内容。"""
    try:
        sid = uuid.UUID(session_id)
    except ValueError as e:
        raise HTTPException(400, "无效的会话 ID") from e

    reply = await stop_chat_session(
        session_id=sid,
        reply=(req.reply if req else None) or "",
        db=db,
    )
    return {"ok": True, "reply": reply}


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    if not req.message.strip():
        raise HTTPException(400, "消息不能为空")

    session, history, _ = await prepare_chat_session(
        session_id=req.session_id,
        message=req.message,
        db=db,
    )
    session_id_str = str(session.id)
    agent_id, oc_model, oc_user = resolve_openclaw_route(
        session_id_str,
        skill_name=req.selected_skill_name,
        skill_category=req.selected_skill_category,
    )

    messages_for_openclaw = _build_openclaw_messages(
        req, history, mammoth_session_id=session_id_str
    )

    try:
        reply, usage = await chat_completion(
            messages_for_openclaw,
            session_id=session_id_str,
            agent_id=agent_id,
            model=oc_model,
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

    return ChatResponse(session_id=session_id_str, reply=reply, usage=usage)


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
    agent_id, oc_model, oc_user = resolve_openclaw_route(
        session_id_str,
        skill_name=req.selected_skill_name,
        skill_category=req.selected_skill_category,
    )
    messages_for_openclaw = _build_openclaw_messages(
        req, history, mammoth_session_id=session_id_str
    )
    had_history = bool(history)

    async def event_generator():
        content_ended = asyncio.Event()
        seen_record_ids: set[str] = set()
        seen_content_ids: set[str] = set()
        chunks: list[str] = []
        followup_texts: list[str] = []
        live_steps: list[dict] = []
        last_steps_sig = ""
        client_stream = ClientStreamFilter()
        queue: asyncio.Queue[tuple[str, dict | str]] = asyncio.Queue()
        stream_error: str | None = None
        stream_budget = estimate_stream_budget(
            req.message,
            skill_name=req.selected_skill_name,
        )

        session_payload = {
            "session_id": session_id_str,
            "stream_budget_sec": stream_budget.max_wait_after_content_sec,
            "post_tool_idle_sec": stream_budget.post_tool_idle_sec,
            "molecule_count": stream_budget.molecule_count,
            "openclaw_agent_id": agent_id,
            "openclaw_model": oc_model,
            "openclaw_user": oc_user,
        }
        yield _sse("session", session_payload)
        append_process_event(session_id_str, {"type": "session", **session_payload})

        async def pump_content() -> None:
            nonlocal stream_error
            try:
                async for delta in chat_completion_stream(
                    messages_for_openclaw,
                    session_id=session_id_str,
                    agent_id=agent_id,
                    model=oc_model,
                ):
                    sanitized = sanitize_user_facing_text(delta)
                    if not sanitized:
                        continue
                    if sanitized.strip() and is_interm_status_only(sanitized):
                        continue
                    chunks.append(sanitized)
                    append_process_event(session_id_str, {"type": "delta", "content": sanitized})
                    visible = client_stream.feed(sanitized)
                    if visible:
                        await queue.put(("delta", {"content": visible}))
            except OpenClawError as e:
                stream_error = str(e)
                await queue.put(("error", {"message": stream_error}))
            finally:
                content_ended.set()
                await queue.put(("_content_end", {}))

        async def pump_steps() -> None:
            path = await wait_for_session_jsonl(session_id_str, agent_id=agent_id)
            if not path:
                return

            if had_history:
                from openclaw_session_watch import seed_seen_from_session_jsonl

                pre_seen, pre_content = seed_seen_from_session_jsonl(path)
                seen_record_ids.update(pre_seen)
                seen_content_ids.update(pre_content)

            async def emit_step(step: dict) -> None:
                from tool_summarize import polish_ai4drug_exec_step

                # 过程日志保留原始输出；SSE/展示再做友好化摘要
                append_process_event(session_id_str, {"type": "step", **dict(step)})
                polished = polish_ai4drug_exec_step(dict(step))
                await queue.put(("step", polished))

            async def emit_thinking_zh(step: dict) -> None:
                try:
                    zh_step = await normalize_step_zh(step)
                except Exception:
                    zh_step = step
                await emit_step(zh_step)

            try:
                async for kind, payload in watch_session_jsonl(
                    path,
                    seen_record_ids=seen_record_ids,
                    content_ended=content_ended,
                    seen_content_ids=seen_content_ids,
                    idle_long_rounds=stream_budget.idle_long_rounds,
                    max_rounds=stream_budget.max_rounds,
                ):
                    if kind == "content":
                        text = sanitize_user_facing_text(str(payload))
                        if not text or is_interm_status_only(text):
                            continue
                        followup_texts.append(text)
                        append_process_event(session_id_str, {"type": "delta", "content": text})
                        visible = client_stream.feed(text)
                        if visible:
                            await queue.put(("delta", {"content": visible}))
                        continue
                    step = payload
                    if step.get("kind") == "thinking":
                        # 顺序写入：思考必须在同条记录的工具调用之前展示
                        await emit_thinking_zh(step)
                    else:
                        await emit_step(step)
            finally:
                pass

        content_task = asyncio.create_task(pump_content())
        steps_task = asyncio.create_task(pump_steps())

        loop = asyncio.get_running_loop()
        post_stream_settle_sec = 0.5
        max_wait_after_content_sec = stream_budget.max_wait_after_content_sec
        settle_deadline: float | None = None
        content_ended_at: float | None = None
        idle_after_tools_sec = stream_budget.post_tool_idle_sec
        synthesized_final_emitted = False

        def _step_still_background(step: dict) -> bool:
            blob = f"{step.get('result', '')} {step.get('detail', '')}"
            return (
                "命令仍在后台运行" in blob
                or "后台任务仍在运行" in blob
                or "Command still running" in blob
                or "Process still running" in blob
            )

        def _is_process_poll_done(step: dict) -> bool:
            if str(step.get("status") or "").lower() not in ("done", "failed"):
                return False
            name = str(step.get("name") or "")
            title = str(step.get("title") or "")
            inp = str(step.get("input") or "").lower()
            if name in ("后台进程", "process") or title in ("后台进程", "process"):
                return True
            return "poll" in inp

        def _seal_stale_background_execs() -> None:
            """curl 进后台后由 process poll 取回结果时，收口残留的 running exec。"""
            if not any(_is_process_poll_done(s) for s in live_steps if isinstance(s, dict)):
                return
            for s in live_steps:
                if not isinstance(s, dict):
                    continue
                if str(s.get("status") or "").lower() != "running":
                    continue
                if not _step_still_background(s):
                    continue
                s["status"] = "done"
                s["result"] = "工具执行完成"
                if not s.get("detail"):
                    s["detail"] = ""

        def _has_running_tools() -> bool:
            # 必须看合并后的最新状态；历史中间态「命令仍在后台运行」不能拖住整轮结束
            from reply_rebuild import merge_live_steps
            from tool_summarize import _drop_running_when_done_exists

            merged = _drop_running_when_done_exists(
                merge_live_steps([s for s in live_steps if isinstance(s, dict)])
            )
            has_poll_done = any(_is_process_poll_done(s) for s in merged)
            for s in merged:
                status = str(s.get("status") or "").lower()
                if status in ("done", "failed"):
                    continue
                still_bg = _step_still_background(s)
                # 后台 poll 已完成 ⇒ 此前 still running 的 exec 视为结束，避免空等数分钟
                if still_bg and has_poll_done:
                    continue
                if status == "running" or still_bg:
                    return True
            return False

        try:
            while True:
                try:
                    kind, data = await asyncio.wait_for(queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    kind = None
                    data = None

                if kind is not None:
                    settle_deadline = None
                    if kind != "_content_end":
                        # 工具完成后不要因偶发 step 重置整段长等待
                        if kind == "step" and content_ended.is_set() and not _has_running_tools():
                            pass
                        else:
                            content_ended_at = None
                    if kind == "_content_end":
                        continue
                    if kind == "step":
                        live_steps.append(data)  # type: ignore[arg-type]
                        if isinstance(data, dict) and _is_process_poll_done(data):
                            _seal_stale_background_execs()
                        from reply_rebuild import extract_final_answer, merge_live_steps
                        from skill_display import should_emit_early_final, synthesize_early_final_from_steps
                        from tool_summarize import polish_ai4drug_exec_steps

                        merged = polish_ai4drug_exec_steps(
                            merge_live_steps([s for s in live_steps if isinstance(s, dict)])
                        )
                        if not synthesized_final_emitted and not _has_running_tools():
                            blob = sanitize_user_facing_text(
                                "".join(chunks) + "".join(followup_texts)
                            )
                            if len(extract_final_answer(blob).strip()) < 8:
                                early_final = ""
                                if should_emit_early_final(merged, req.selected_skill_name):
                                    early_final = synthesize_early_final_from_steps(
                                        merged,
                                        req.selected_skill_name,
                                    )
                                if early_final:
                                    delta = f"\n\n## 最终回答\n\n{early_final}\n"
                                    chunks.append(delta)
                                    followup_texts.append(delta)
                                    append_process_event(
                                        session_id_str, {"type": "delta", "content": delta}
                                    )
                                    visible = client_stream.feed(delta)
                                    if visible:
                                        await queue.put(("delta", {"content": visible}))
                                    synthesized_final_emitted = True
                        sig = json.dumps(
                            [
                                (
                                    s.get("tool_call_id"),
                                    s.get("record_id"),
                                    s.get("kind"),
                                    s.get("thinking_seq"),
                                    s.get("status"),
                                    s.get("result"),
                                    s.get("detail"),
                                    s.get("display_block"),
                                )
                                for s in merged
                            ],
                            ensure_ascii=False,
                            default=str,
                        )
                        if sig != last_steps_sig:
                            last_steps_sig = sig
                            yield _sse("steps", {"steps": merged})
                        continue
                    yield _sse(kind, data)  # type: ignore[arg-type]
                    continue

                if not content_ended.is_set() or not queue.empty():
                    continue

                if not steps_task.done():
                    now = loop.time()
                    if content_ended_at is None:
                        content_ended_at = now
                    waited = now - content_ended_at
                    effective_idle = idle_after_tools_sec
                    if synthesized_final_emitted and not _has_running_tools():
                        effective_idle = min(effective_idle, 0.6)
                    # 无 running 工具时：短等待即可结束，避免蛋白/对接完成后空等
                    if not _has_running_tools() and waited >= effective_idle:
                        break
                    if waited >= max_wait_after_content_sec:
                        break
                    continue

                now = loop.time()
                if settle_deadline is None:
                    settle_deadline = now + post_stream_settle_sec
                elif now >= settle_deadline:
                    break
        finally:
            content_task.cancel()
            steps_task.cancel()
            await asyncio.gather(content_task, steps_task, return_exceptions=True)

        streamed = sanitize_user_facing_text("".join(chunks))
        raw_reply = pick_best_assistant_reply([streamed, *followup_texts]) or streamed
        merged_steps = merge_live_steps(live_steps)
        if merged_steps:
            from tool_summarize import polish_ai4drug_exec_steps

            merged_steps = polish_ai4drug_exec_steps(merged_steps, reply=raw_reply)
            merged_steps = await normalize_steps_zh(merged_steps)
        reply = (
            rebuild_reply_with_live_steps(
                raw_reply,
                merged_steps,
                skill_name=req.selected_skill_name,
            )
            if merged_steps and raw_reply and not stream_error
            else raw_reply
        )
        if reply and not stream_error:
            save_task = asyncio.create_task(
                save_assistant_reply(
                    session=session,
                    reply=reply,
                    user_message=req.message,
                    had_history=had_history,
                )
            )
        else:
            save_task = None

        # 完整 steps 写入过程日志；SSE 只发精简 payload，避免超大 JSON 卡住浏览器
        snap = read_process_log_snapshot(session_id_str)
        if snap.get("in_progress") or not snap.get("done_in_file"):
            append_process_done(
                session_id_str,
                reply=reply,
                error=stream_error,
                steps=merged_steps,
            )
        client_done = {
            "type": PROCESS_LOG_DONE_TYPE,
            "tag": PROCESS_LOG_DONE_TAG,
            "session_id": session_id_str,
            "reply": reply,
            "error": stream_error,
            "ok": stream_error is None,
            "steps": merged_steps,
        }
        yield _sse(PROCESS_LOG_DONE_TYPE, client_done)
        yield _sse("done", client_done)

        if save_task is not None:
            await save_task

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions/{session_id}/process-log", response_model=ProcessLogSnapshotOut)
async def get_process_log_snapshot(session_id: str, db: AsyncSession = Depends(get_db)):
    """返回过程日志快照；刷新页面后用于恢复未完成的分析过程。"""
    snap = await prepare_process_log_snapshot(session_id, db)
    return ProcessLogSnapshotOut(**snap)


@app.get("/api/sessions/{session_id}/process-log/stream")
async def stream_process_log(session_id: str, after: int = 0):
    """Tail the per-session process log file and push new lines as SSE.

    读到结束标签 <<<MAMMOTH_DONE>>> / type=mammoth_done 后立刻关闭流。
    """

    async def tail_generator():
        # 读：按日期目录查找；文件尚未创建时等写入落到当天目录
        path = find_process_log(session_id)
        offset = max(0, after)
        idle_rounds = 0
        max_idle = settings.stream_max_sec / settings.stream_poll_interval_sec
        tail_stream = ClientStreamFilter()
        if path and path.exists():
            try:
                head = path.read_text(encoding="utf-8", errors="replace")[:65536]
                rows: list[dict] = []
                for line in head.splitlines():
                    line = line.strip()
                    if not line or line == PROCESS_LOG_DONE_TAG:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                budget = budget_from_process_log(rows)
                if budget is not None:
                    max_idle = budget.idle_long_rounds
            except OSError:
                pass

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
                                elif row.get("type") == "step":
                                    from tool_summarize import polish_ai4drug_exec_step

                                    row = polish_ai4drug_exec_step(row)
                                elif row.get("type") == "delta":
                                    visible = tail_stream.feed(str(row.get("content") or ""))
                                    if not visible:
                                        continue
                                    row = {**row, "content": visible}
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
