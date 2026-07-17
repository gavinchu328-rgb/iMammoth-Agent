import httpx

from config import settings


class OpenClawError(Exception):
    pass


async def chat_completion(messages: list[dict]) -> tuple[str, dict | None]:
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openclaw_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"messages": messages, "model": settings.openclaw_model}

    async with httpx.AsyncClient(timeout=600.0) as client:
        try:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise OpenClawError(f"OpenClaw 请求失败: {e}") from e

    data = resp.json()
    reply = data["choices"][0]["message"]["content"]
    usage = data.get("usage")
    return reply, usage


async def health_check() -> bool:
    url = f"{settings.openclaw_base_url}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openclaw_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                headers=headers,
                json={"messages": [{"role": "user", "content": "ping"}], "model": settings.openclaw_model},
            )
            return resp.status_code == 200
    except httpx.HTTPError:
        return False
