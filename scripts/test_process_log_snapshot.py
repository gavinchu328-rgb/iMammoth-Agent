#!/usr/bin/env python3
"""Multi-turn process log snapshot isolation."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from process_log_store import read_process_log_snapshot  # noqa: E402

SID = "test-multi-turn-isolation"


def _write_log(path: Path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def test_active_turn_only_after_prior_done() -> None:
    log = """
{"type": "delta", "content": "第一轮正文"}
{"type": "step", "kind": "tool", "title": "靶点发现", "status": "done", "name": "靶点发现"}
{"type": "mammoth_done", "tag": "<<<MAMMOTH_DONE>>>", "reply": "第一轮回复"}
<<<MAMMOTH_DONE>>>
{"type": "delta", "content": "第二轮正文"}
{"type": "step", "kind": "tool", "title": "口袋预测", "status": "done", "name": "口袋预测"}
"""
    with tempfile.TemporaryDirectory() as td:
        log_path = Path(td) / f"{SID}.jsonl"
        _write_log(log_path, log)
        with patch("process_log_store.find_process_log", return_value=log_path):
            snap = read_process_log_snapshot(SID)

    assert snap["content"] == "第二轮正文", snap["content"]
    titles = [s.get("title") for s in snap["steps"]]
    assert "靶点发现" not in titles, titles
    assert any("口袋" in (t or "") for t in titles), titles
    assert not snap["done"], snap


def main() -> None:
    test_active_turn_only_after_prior_done()
    print("ok: process log snapshot isolation")


if __name__ == "__main__":
    main()
