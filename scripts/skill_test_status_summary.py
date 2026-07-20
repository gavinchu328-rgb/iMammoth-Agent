#!/usr/bin/env python3
"""Print a concise status summary for scientific skill testing."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path

PROGRESS = Path("/tmp/sci_skill_test_progress.json")
RESULTS = Path("/tmp/sci_skill_test_results.jsonl")
LOG = Path("/tmp/skill_test_batch1.log")
TOTAL = 149


def main() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*60}")
    print(f"技能测试汇总 @ {now}")
    print(f"{'='*60}")

    if not PROGRESS.exists():
        print("进度文件不存在，测试尚未开始或已重置。")
        return

    prog = json.loads(PROGRESS.read_text(encoding="utf-8"))
    done = prog.get("done", {})
    last_idx = prog.get("last_index", -1)

    by_status = Counter(v.get("status") for v in done.values())
    ok = by_status.get("OK", 0)
    fail = by_status.get("FAIL", 0) + by_status.get("HTTP_ERR", 0)
    weak = by_status.get("WEAK", 0)
    import_err = by_status.get("IMPORT_ERR", 0)
    timeout = sum(1 for v in done.values() if "timed out" in (v.get("snippet") or ""))

    print(f"进度: {len(done)}/{TOTAL} ({100*len(done)/TOTAL:.1f}%)")
    print(f"  OK: {ok}  |  FAIL: {fail}  |  WEAK: {weak}  |  IMPORT_ERR: {import_err}  |  超时: {timeout}")
    print(f"当前索引: {last_idx + 1}/{TOTAL}")

    # deps issues
    dep_fail = [sid for sid, v in done.items() if not v.get("deps_ok")]
    if dep_fail:
        print(f"依赖未装齐 ({len(dep_fail)}): {', '.join(dep_fail[:8])}{'...' if len(dep_fail)>8 else ''}")

    # recent results
    recent = sorted(done.values(), key=lambda x: x.get("index", 0))[-5:]
    if recent:
        print("\n最近 5 个:")
        for v in recent:
            sid = v.get("id", "?")
            st = v.get("status", "?")
            el = v.get("elapsed", "?")
            snip = (v.get("snippet") or "")[:60].replace("\n", " ")
            print(f"  [{st:6}] {sid} ({el}s) {snip}")

    # running?
    import subprocess

    r = subprocess.run(
        ["pgrep", "-f", "test_sci_skills_one_by_one.py"],
        capture_output=True,
        text=True,
    )
    if r.stdout.strip():
        print(f"\n测试进程: 运行中 (pid {r.stdout.strip().split()[0]})")
    else:
        print("\n测试进程: 未运行")

    if LOG.exists():
        tail = LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
        if tail:
            print("\n日志末尾:")
            for line in tail:
                print(f"  {line[:100]}")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
