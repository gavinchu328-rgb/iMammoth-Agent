#!/usr/bin/env python3
"""Compare page-display final answer vs raw stream for skill sessions."""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from content_filters import _final_answer_quality_score, has_rich_markdown_report  # noqa: E402
from reply_rebuild import extract_final_answer, rebuild_reply_with_live_steps, merge_live_steps  # noqa: E402
from tool_summarize import polish_ai4drug_exec_steps  # noqa: E402

BASE = "http://127.0.0.1:8080"

SESSIONS: dict[str, str] = {
    "分子设计": "fa54a746-f2e5-4e4a-b7ab-47b282643c96",
    "3D构象生成": "df3e82a9-c3e2-4601-a18c-df0bd75c73bb",
    "受体准备": "5007f138-c8ee-411b-99ef-e73f9b996d4d",
    "配体准备": "a72e9013-9262-4e67-9e99-a1a594f91b5f",
    "对接盒配置": "39390530-ef63-4b2e-9d88-22e46a7ded3f",
    "分子对接": "19240bc3-f745-44f9-96e5-00ddc19a398b",
    "ADMET评估": "052ceb1a-e21a-40cd-ba27-a531b7b431a6",
    "逆合成分析": "a72e9013-9262-4e67-9e99-a1a594f91b5f",
}


def load_log(sid: str) -> tuple[str, list[dict], str]:
    for day in sorted((ROOT / "process_logs").iterdir(), reverse=True):
        p = day / f"{sid}.jsonl"
        if not p.exists():
            continue
        chunks, steps, done = [], [], ""
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") == "delta" and row.get("content"):
                chunks.append(str(row["content"]))
            if row.get("type") == "step" and row.get("kind"):
                steps.append(row)
            if row.get("type") == "mammoth_done":
                done = str(row.get("reply") or "")
        return "".join(chunks), steps, done
    raise FileNotFoundError(sid)


def api_process(sid: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/api/sessions/{sid}/process-log", timeout=30) as r:
        return json.loads(r.read())


def api_session(sid: str) -> dict:
    with urllib.request.urlopen(f"{BASE}/api/sessions/{sid}", timeout=30) as r:
        return json.loads(r.read())


def display_final_from_db(sid: str) -> str:
    sess = api_session(sid)
    for m in reversed(sess.get("messages") or []):
        if m.get("role") == "assistant":
            content = str(m.get("content") or "")
            return extract_final_answer(content)
    return ""


def main() -> int:
    failed = 0
    print("SKILL\tTOOLS\tRAW_F\tAPI_F\tDB_F\tHEAL_F\tPAGE_OK\tISSUE")
    for skill, sid in SESSIONS.items():
        try:
            stream, steps, done = load_log(sid)
            merged = polish_ai4drug_exec_steps(merge_live_steps(steps), reply=done or stream)
            raw_f = extract_final_answer(stream)
            api_snap = api_process(sid)
            api_f = extract_final_answer(str(api_snap.get("reply") or done))
            db_f = display_final_from_db(sid)
            heal_f = extract_final_answer(
                rebuild_reply_with_live_steps(stream, merged, skill_name=skill)
            )
            tools = sum(1 for s in merged if s.get("kind") in ("tool", "skill", "web"))
            issues: list[str] = []
            if tools == 0:
                issues.append("no_tools")
            if not raw_f and not api_f:
                issues.append("empty_raw")
            if db_f and raw_f and len(db_f) < len(raw_f) * 0.55:
                issues.append("db_truncated")
            if db_f and heal_f and _final_answer_quality_score(heal_f) > _final_answer_quality_score(db_f) + 80:
                issues.append("needs_heal")
            if db_f.startswith("**") and has_rich_markdown_report(raw_f) and not has_rich_markdown_report(db_f):
                issues.append("bullet_only")
            page_ok = not issues or issues == ["needs_heal"]
            if issues:
                failed += 1
            print(
                f"{skill}\t{tools}\t{len(raw_f)}\t{len(api_f)}\t{len(db_f)}\t{len(heal_f)}\t"
                f"{'OK' if page_ok else 'FAIL'}\t{';'.join(issues) or 'ok'}"
            )
        except Exception as e:
            failed += 1
            print(f"{skill}\tERR\t\t\t\t\tFAIL\t{e}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
