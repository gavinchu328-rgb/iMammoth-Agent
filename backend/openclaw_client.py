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


async def chat_completion(
    messages: list[dict],
    *,
    session_id: str | None = None,
) -> tuple[str, dict | None]:
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    payload = {
        "messages": messages,
        "model": settings.openclaw_model,
        "user": _openclaw_user_id(session_id),
        "stream": False,
        "max_tokens": 64000,
    }

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


async def health_check() -> bool:
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                headers=_openclaw_headers(),
                json={
                    "messages": [{"role": "user", "content": "ping"}],
                    "model": settings.openclaw_model,
                    "user": _openclaw_user_id(None),
                    "stream": False,
                },
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
