"""Filter assistant stream chunks before they reach the browser.

Live steps are shown in the process panel; suppress duplicate process
templates and raw tool JSON in the text stream.
"""

from __future__ import annotations

import re

from text_sanitize import sanitize_user_facing_text

# 模型流式输出常把 Markdown 标题压成无空格格式（##分析过程）
_PROCESS_MARKERS = (
    "## 分析过程",
    "##分析过程",
    "### 步骤",
    "###步骤",
)
_FINAL_MARKERS = ("## 最终回答", "##最终回答")

_SESSION_RETRY_MONOLOGUE = re.compile(
    r"发现\s*API\s*返回了自动生成的\s*session_id|"
    r"需要用正确\s*session_id\s*重试|"
    r"现在用正确的\s*session_id|"
    r"第二个使用正确\s*session_id\s*的\s*conformer",
    re.I,
)

_ORPHAN_EMOJI_ONLY = re.compile(
    r"^\s*[\U0001F300-\U0001FAFF\U00002600-\U000027BF]+\s*$"
)


def _find_first_marker(buf: str, markers: tuple[str, ...]) -> int:
    idx = -1
    for marker in markers:
        pos = buf.find(marker)
        if pos >= 0 and (idx < 0 or pos < idx):
            idx = pos
    return idx


def _looks_like_collapsed_process_dump(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if "工具数:" in t and ("步骤" in t or "###" in t):
        return True
    if re.search(r"-\s*类型:\s*工具", t) and "结果摘要" in t:
        return True
    if "ai4drug__" in t and ("输入摘要" in t or "结果摘要" in t):
        return True
    return False


def _looks_like_json_fragment(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _looks_like_collapsed_process_dump(t):
        return True
    if t.startswith("{") or t.startswith("["):
        return True
    if '"success"' in t and ("{" in t or "[" in t):
        return True
    if re.search(r'"\w+"\s*:\s*', t) and len(t) > 24:
        return True
    return False


def _find_last_marker(buf: str, markers: tuple[str, ...]) -> int:
    idx = -1
    for marker in markers:
        pos = buf.rfind(marker)
        if pos >= 0 and (idx < 0 or pos > idx):
            idx = pos
    return idx


def _is_process_header_prefix(buf: str) -> bool:
    """True while buffer is building toward ## 分析过程 (incl. token-split fragments)."""
    t = (buf or "").lstrip()
    if not t:
        return False
    if re.match(r"^#{0,3}\s*分析", t):
        return True
    if re.match(r"^#{0,3}分析", t):
        return True
    if t in ("分析", "分析过程") or t.startswith("分析过程"):
        return True
    if re.fullmatch(r"#+\s*", t):
        return True
    return False


def _safe_stream_preamble(text: str) -> bool:
    t = (text or "").lstrip()
    if not t:
        return False
    if _ORPHAN_EMOJI_ONLY.match(t.strip()):
        return False
    if _SESSION_RETRY_MONOLOGUE.search(t):
        return False
    if _is_process_header_prefix(t):
        return False
    if _looks_like_collapsed_process_dump(t):
        return False
    return True


class ClientStreamFilter:
    """Forward only preamble + ## 最终回答 body; drop ## 分析过程 dumps."""

    def __init__(self) -> None:
        self._buf = ""
        self._forwarded_final_len = 0
        self._forwarded_preamble_len = 0

    def feed(self, chunk: str) -> str:
        raw = sanitize_user_facing_text(chunk)
        if not raw:
            return ""
        if "<tool_call" in raw.lower():
            return ""
        if _ORPHAN_EMOJI_ONLY.match(raw.strip()):
            return ""
        if _looks_like_json_fragment(raw):
            return ""

        self._buf += raw
        out: list[str] = []

        final_idx = _find_last_marker(self._buf, _FINAL_MARKERS)
        if final_idx >= 0:
            marker = next(m for m in _FINAL_MARKERS if self._buf.rfind(m) == final_idx)
            final_start = final_idx + len(marker)
            final_body = self._buf[final_start:]
            proc_in_final = _find_first_marker(final_body, _PROCESS_MARKERS)
            if proc_in_final >= 0:
                final_body = final_body[:proc_in_final]
            # 模型可能在首个 ## 最终回答 后插入过程模板，再输出真正的最终回答
            if self._forwarded_final_len > len(final_body):
                self._forwarded_final_len = 0
            if len(final_body) > self._forwarded_final_len:
                piece = final_body[self._forwarded_final_len :]
                if self._forwarded_final_len == 0:
                    piece = piece.lstrip()
                out.append(piece)
                self._forwarded_final_len = len(final_body)
            return "".join(out)

        proc_idx = _find_first_marker(self._buf, _PROCESS_MARKERS)
        if proc_idx < 0 and _looks_like_collapsed_process_dump(self._buf):
            proc_idx = 0

        if proc_idx >= 0:
            preamble = self._buf[:proc_idx]
            if len(preamble) > self._forwarded_preamble_len:
                piece = preamble[self._forwarded_preamble_len :]
                if _safe_stream_preamble(piece):
                    out.append(piece)
                self._forwarded_preamble_len = len(preamble)
            return "".join(out)

        # No process/final markers yet: stream safe preamble only.
        if _is_process_header_prefix(self._buf):
            return ""
        if len(self._buf) > self._forwarded_preamble_len:
            delta = self._buf[self._forwarded_preamble_len :]
            self._forwarded_preamble_len = len(self._buf)
            if _safe_stream_preamble(delta):
                return delta
        return ""
