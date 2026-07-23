import json
from collections.abc import AsyncIterator

import httpx

from config import settings
from openclaw_route import openclaw_user_id


class OpenClawError(Exception):
    pass


def _openclaw_headers(agent_id: str | None = None) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openclaw_api_key}",
        "Content-Type": "application/json",
        "x-openclaw-agent-id": (agent_id or settings.openclaw_agent_id).strip(),
    }


def _chat_payload(
    messages: list[dict],
    *,
    session_id: str,
    stream: bool,
    model: str | None = None,
) -> dict:
    # 对齐 AI4Drug：user=conv:<session> 固定绑定 OpenClaw 服务端会话
    return {
        "messages": messages,
        "model": (model or settings.openclaw_model).strip(),
        "user": openclaw_user_id(session_id),
        "stream": stream,
        "max_tokens": 64000,
    }


async def chat_completion(
    messages: list[dict],
    *,
    session_id: str,
    agent_id: str | None = None,
    model: str | None = None,
) -> tuple[str, dict | None]:
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    payload = _chat_payload(messages, session_id=session_id, stream=False, model=model)

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            resp = await client.post(
                url,
                headers=_openclaw_headers(agent_id),
                json=payload,
            )
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OpenClawError(f"OpenClaw 请求失败: {e}") from e

    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    usage = data.get("usage")
    return reply, usage


async def chat_completion_stream(
    messages: list[dict],
    *,
    session_id: str,
    agent_id: str | None = None,
    model: str | None = None,
) -> AsyncIterator[str]:
    """Yield assistant text deltas from OpenClaw SSE stream."""
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    payload = _chat_payload(messages, session_id=session_id, stream=True, model=model)

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            async with client.stream(
                "POST",
                url,
                headers=_openclaw_headers(agent_id),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
        except httpx.HTTPError as e:
            raise OpenClawError(f"OpenClaw 请求失败: {e}") from e


async def ping_openclaw() -> bool:
    """Lightweight OpenClaw reachability check (no LLM call)."""
    url = f"{settings.openclaw_base_url}/v1/models"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url, headers=_openclaw_headers())
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
