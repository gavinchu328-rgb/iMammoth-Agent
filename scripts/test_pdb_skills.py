#!/usr/bin/env python3
"""Smoke tests for PDB skill backends and optional chat integration."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8080/api"
CHAT_TIMEOUT = 600

DB_TESTS = [
    (
        "PDB 文本搜索",
        "rcsb-pdb-text",
        "MCP chemotaxis protein",
        lambda r: (r.get("total_count") or 0) > 0 and bool(r.get("hits"))
        and any(h.get("resolution") is not None for h in (r.get("hits") or []) if isinstance(h, dict)),
    ),
    (
        "PDB 元数据查询",
        "rcsb-pdb-metadata",
        "4Z9H",
        lambda r: r.get("pdb_id") == "4Z9H"
        and r.get("resolution") is not None
        and bool(r.get("ligands")),
    ),
    (
        "PDB 结构下载",
        "rcsb-pdb",
        "1M17",
        lambda r: r.get("query") == "1M17" and bool(r.get("download_url")),
    ),
]

SKILL_CHAT_TESTS = [
    (
        "PDB 文本搜索",
        "帮我找找 MCP 蛋白（细菌趋化）的高分辨率结构",
        ["pdb", "4", "结构", "mcp", "搜索", "匹配"],
    ),
    (
        "PDB 元数据查询",
        "查询 PDB 4Z9H 的分辨率、实验方法和配体信息",
        ["4z9h", "分辨率", "实验", "方法"],
    ),
    (
        "PDB 结构下载",
        "下载 EGFR 结构 1M17 的 PDB 文件并预览三维结构",
        ["1m17", "下载", "pdb", "egfr"],
    ),
]


def post_json(path: str, payload: dict, *, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        f"{API}{path}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def build_skill_prompt(skill_id: str, name: str, category: str, description: str) -> str:
    lines = [
        f"本轮对话请优先匹配并调用与「{name}」对应的技能/工具。",
        f"技能分类：{category}。",
        f"技能说明：{description}。",
        "优先按这个技能的能力范围来理解用户问题；如果存在对应的 OpenClaw skill、MCP 工具或内置工具，请先调用它，而不是直接凭记忆作答。",
        "如果该技能能够产生结构化结果，请先拿到结果再组织中文回答。",
    ]
    if skill_id == "pdb-text-search":
        lines += [
            "禁止 read database-lookup、禁止 sessions_spawn、禁止凭记忆编造 PDB 结果。",
            "禁止 curl data.rcsb.org、search.rcsb.org 或手写 RCSB 脚本。",
            "必须且仅通过 exec 调用猛犸内置接口（只调用一次）：",
            "curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb-text/search -H 'Content-Type: application/json' -d '{\"query\":\"<关键词>\"}'",
            "结果已按分辨率从高到低排序；解析 total_count 与 hits[].pdb_id、hits[].resolution，直接列出前 10 条即可。",
        ]
    elif skill_id == "pdb-metadata-lookup":
        lines += [
            "禁止 read database-lookup、禁止 sessions_spawn、禁止凭记忆编造元数据。",
            "禁止 curl data.rcsb.org、search.rcsb.org；query 必须是 4 位 PDB ID。",
            "必须且仅通过 exec 调用猛犸内置接口（只调用一次）：",
            "curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb-metadata/search -H 'Content-Type: application/json' -d '{\"query\":\"<PDB_ID>\"}'",
            "解析 resolution、experimental_method、title、release_date、ligands[]；禁止为配体 entity 再调接口。",
        ]
    elif skill_id == "pdb-structure-download":
        lines += [
            "禁止 read database-lookup、禁止 sessions_spawn。",
            "必须且仅通过 exec 调用猛犸内置接口（一次即可）：",
            "curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb/search -H 'Content-Type: application/json' -d '{\"query\":\"<PDB_ID>\"}'",
            "返回 download_url、thumbnail_url、reachable；步骤标题写「PDB 结构下载」。",
        ]
    return "\n".join(lines)


def test_database_apis() -> list[tuple[str, bool, str]]:
    results: list[tuple[str, bool, str]] = []
    for name, db_id, query, validator in DB_TESTS:
        try:
            out = post_json(f"/databases/{db_id}/search", {"query": query})
            result = out.get("result") or {}
            ok = not out.get("error") and validator(result)
            detail = json.dumps(result, ensure_ascii=False)[:240]
            results.append((name, ok, detail))
        except Exception as e:
            results.append((name, False, str(e)))
    return results


def test_chat_skill(name: str, message: str, keywords: list[str], skill_id: str) -> tuple[bool, str]:
    skill_meta = {
        "pdb-text-search": ("PDB 文本搜索", "蛋白结构", "在 RCSB PDB 中按关键词搜索蛋白结构"),
        "pdb-metadata-lookup": ("PDB 元数据查询", "蛋白结构", "按 PDB ID 查询分辨率、实验方法等"),
        "pdb-structure-download": ("PDB 结构下载", "蛋白结构", "下载 PDB 结构文件"),
    }
    sname, category, desc = skill_meta[skill_id]
    payload = {
        "message": message,
        "session_id": None,
        "selected_skill_name": sname,
        "selected_skill_category": category,
        "selected_skill_system_prompt": build_skill_prompt(skill_id, sname, category, desc),
    }
    t0 = time.time()
    out = post_json("/chat", payload, timeout=CHAT_TIMEOUT)
    reply = (out.get("reply") or "").lower()
    elapsed = time.time() - t0
    hits = [k for k in keywords if k.lower() in reply]
    ok = len(reply) > 80 and len(hits) >= 2
    return ok, f"elapsed={elapsed:.0f}s len={len(reply)} hits={hits}"


def main() -> int:
    print("== PDB database API tests ==")
    api_ok = True
    for name, ok, detail in test_database_apis():
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: {detail}")
        api_ok = api_ok and ok

    run_chat = "--chat" in sys.argv
    if not run_chat:
        print("\n(database API only; add --chat to run slow agent integration tests)")
        return 0 if api_ok else 1

    if not api_ok:
        print("\nSkip chat tests because database APIs failed.")
        return 1

    print("\n== PDB skill chat tests (slow) ==")
    chat_ok = True
    skill_ids = ["pdb-text-search", "pdb-metadata-lookup", "pdb-structure-download"]
    for (name, message, keywords), skill_id in zip(SKILL_CHAT_TESTS, skill_ids):
        try:
            ok, detail = test_chat_skill(name, message, keywords, skill_id)
            status = "PASS" if ok else "FAIL"
            print(f"{status} {name}: {detail}")
            chat_ok = chat_ok and ok
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            print(f"FAIL {name}: HTTP {e.code} {body[:200]}")
            chat_ok = False
        except Exception as e:
            print(f"FAIL {name}: {e}")
            chat_ok = False

    return 0 if api_ok and chat_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
