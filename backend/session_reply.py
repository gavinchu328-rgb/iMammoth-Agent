"""Build and persist assistant replies for stop / heal flows."""

from __future__ import annotations

STOPPED_MARKER = "（已停止生成）"


def ensure_stopped_reply(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return STOPPED_MARKER
    if STOPPED_MARKER in body:
        return body
    return f"{body.rstrip()}\n\n{STOPPED_MARKER}"


def reply_from_done_snapshot(snap: dict, fallback: str = "") -> str:
    existing = str(snap.get("reply") or fallback or "").strip()
    return existing or STOPPED_MARKER


def build_stopped_reply_from_snapshot(snap: dict, partial_reply: str = "") -> str:
    from reply_rebuild import rebuild_reply_with_live_steps

    steps = snap.get("steps") or []
    content = (partial_reply or snap.get("content") or "").strip()
    if steps and content:
        rebuilt = rebuild_reply_with_live_steps(content, steps)
    else:
        rebuilt = content
    return ensure_stopped_reply(rebuilt)
