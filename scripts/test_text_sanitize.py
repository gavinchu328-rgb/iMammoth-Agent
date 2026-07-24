#!/usr/bin/env python3
"""Ensure streaming deltas preserve newlines."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from text_sanitize import is_interm_status_only, sanitize_user_facing_text


def main() -> None:
    assert sanitize_user_facing_text("\n") == "\n"
    assert sanitize_user_facing_text("\n\n") == "\n\n"
    assert sanitize_user_facing_text("## 分析过程\n") == "## 分析过程\n"
    assert sanitize_user_facing_text("\n- 步骤 1") == "\n- 步骤 1"
    assert sanitize_user_facing_text("hello\nworld") == "hello\nworld"
    assert not (sanitize_user_facing_text("\n").strip() and is_interm_status_only("\n"))
    assert is_interm_status_only("猛犸智能体正在处理您的请求…")
    print("ok: text_sanitize preserves newlines")


if __name__ == "__main__":
    main()
