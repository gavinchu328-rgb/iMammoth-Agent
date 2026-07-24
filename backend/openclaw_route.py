"""OpenClaw agent routing: sticky user=conv:{session} + skill-based agent.

对齐 AI4Drug 调用约定：
- Header: x-openclaw-agent-id
- Body:   model=openclaw:<agent> , user=conv:<猛犸 session UUID>

同一猛犸会话必须固定同一 OpenClaw agent + 同一 user，否则工具上下文会落到
不同 OpenClaw session（agent:xxx:openai:<随机>），导致后续步骤读不到前序结果。
"""

from __future__ import annotations

import json
from pathlib import Path

from config import settings

_AI4DRUG_SKILL_NAMES = frozenset(
    {
        "靶点发现",
        "蛋白质获取",
        "口袋预测",
        "分子设计",
        "3D构象生成",
        "受体准备",
        "配体准备",
        "对接盒配置",
        "分子对接",
        "ADMET评估",
        "逆合成分析",
        "端到端药物发现",
        "流程汇总",
    }
)

_AI4DRUG_CATEGORIES = frozenset({"AI4Drug", "ai4drug"})


def openclaw_user_id(session_id: str | None) -> str:
    """OpenClaw 按 user 字段复用服务端会话；必须稳定且唯一。"""
    sid = (session_id or "").strip()
    if not sid:
        raise ValueError("openclaw user 需要猛犸 session_id，禁止 anonymous")
    if sid.startswith("conv:"):
        return sid
    return f"conv:{sid}"


def _meta_path(session_id: str) -> Path:
    root = Path(settings.process_log_dir)
    if not root.is_absolute():
        root = Path(__file__).parent / root
    meta_dir = root / "_session_meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    return meta_dir / f"{session_id}.json"


def _read_route_meta(session_id: str) -> dict | None:
    path = _meta_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_sticky_agent(session_id: str) -> str | None:
    meta = _read_route_meta(session_id)
    if not meta:
        return None
    agent = str(meta.get("openclaw_agent_id") or "").strip()
    return agent or None


def save_sticky_agent(session_id: str, agent_id: str, *, model: str | None = None) -> None:
    path = _meta_path(session_id)
    payload = {
        "openclaw_agent_id": agent_id,
        "openclaw_model": model or f"openclaw:{agent_id}",
        "openclaw_user": openclaw_user_id(session_id),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def is_ai4drug_skill(
    skill_name: str | None = None,
    skill_category: str | None = None,
) -> bool:
    name = (skill_name or "").strip()
    cat = (skill_category or "").strip()
    if name in _AI4DRUG_SKILL_NAMES:
        return True
    if cat in _AI4DRUG_CATEGORIES:
        return True
    if name.startswith("ai4drug") or "AI4Drug" in name:
        return True
    return False


def _route_from_meta(sticky: str, meta: dict | None) -> tuple[str, str]:
    model = f"openclaw:{sticky}" if not sticky.startswith("openclaw:") else sticky
    if meta:
        model = str(meta.get("openclaw_model") or model)
        agent = str(meta.get("openclaw_agent_id") or sticky)
    else:
        agent = sticky
        model = f"openclaw:{agent}" if not model.startswith("openclaw:") else model
    return agent, model


def _default_route(wants_ai4drug: bool) -> tuple[str, str]:
    if wants_ai4drug:
        return settings.openclaw_ai4drug_agent_id, settings.openclaw_ai4drug_model
    agent = settings.openclaw_agent_id
    model = settings.openclaw_model
    if model.strip() in ("", "openclaw"):
        model = f"openclaw:{agent}"
    return agent, model


def resolve_openclaw_route(
    session_id: str,
    *,
    skill_name: str | None = None,
    skill_category: str | None = None,
) -> tuple[str, str, str]:
    """Return (agent_id, model, user).

    Sticky by default so tool context stays on one OpenClaw agent/user.
    Exception: upgrade main → ai4drug when the user explicitly selects an AI4Drug skill.
    """
    user = openclaw_user_id(session_id)
    wants_ai4drug = is_ai4drug_skill(skill_name, skill_category)
    ai4drug_agent = settings.openclaw_ai4drug_agent_id

    sticky = load_sticky_agent(session_id)
    if sticky:
        if wants_ai4drug and sticky != ai4drug_agent:
            agent, model = ai4drug_agent, settings.openclaw_ai4drug_model
            save_sticky_agent(session_id, agent, model=model)
            return agent, model, user
        return *_route_from_meta(sticky, _read_route_meta(session_id)), user

    agent, model = _default_route(wants_ai4drug)
    save_sticky_agent(session_id, agent, model=model)
    return agent, model, user
