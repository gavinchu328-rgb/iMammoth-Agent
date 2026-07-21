import json
from collections.abc import AsyncIterator

import httpx

from config import settings


class OpenClawError(Exception):
    pass


def _openclaw_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openclaw_api_key}",
        "Content-Type": "application/json",
        "x-openclaw-agent-id": settings.openclaw_agent_id,
    }


def _openclaw_user_id(session_id: str | None) -> str:
    # OpenClaw keys server-side session state by the "user" field.
    # AI4Drug uses conv:<id> so the same conversation appears in Control UI.
    return f"conv:{session_id or 'anonymous'}"


def _chat_payload(messages: list[dict], *, session_id: str | None, stream: bool) -> dict:
    return {
        "messages": messages,
        "model": settings.openclaw_model,
        "user": _openclaw_user_id(session_id),
        "stream": stream,
        "max_tokens": 64000,
    }


async def chat_completion(
    messages: list[dict],
    *,
    session_id: str | None = None,
) -> tuple[str, dict | None]:
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    payload = _chat_payload(messages, session_id=session_id, stream=False)

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            resp = await client.post(url, headers=_openclaw_headers(), json=payload)
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
    session_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield assistant text deltas from OpenClaw SSE stream."""
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    payload = _chat_payload(messages, session_id=session_id, stream=True)

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            async with client.stream(
                "POST",
                url,
                headers=_openclaw_headers(),
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
