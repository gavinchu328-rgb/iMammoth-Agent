#!/usr/bin/env python3
"""Test AI4Drug skills (靶点发现→逆合成) via stream API; validate process display."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8080"
TIMEOUT = 900

SKILLS: list[tuple[str, str, str]] = [
    ("靶点发现", "帮我找一下肺癌的药物靶点", "AI4Drug"),
    ("蛋白质获取", "帮我获取 EGFR_3W2S 蛋白的三维结构信息", "AI4Drug"),
    ("口袋预测", "帮我预测 EGFR（PDB: 3W2S）上有哪些可能的结合口袋", "AI4Drug"),
    (
        "分子设计",
        "针对 EGFR（PDB: 3W2S）口袋 EGFR_3W2S_pocket1，帮我设计 3 个候选小分子",
        "AI4Drug",
    ),
    (
        "3D构象生成",
        "帮我给阿司匹林（SMILES: CC(=O)Oc1ccccc1C(=O)O）生成三维构象，session 用当前猛犸会话",
        "AI4Drug",
    ),
    (
        "受体准备",
        "帮我把 EGFR 蛋白结构（PDB: 3W2S）准备成可以做分子对接的受体",
        "AI4Drug",
    ),
    (
        "配体准备",
        "帮我把吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）准备成对接配体，"
        "molecule id 用 EGFR_3W2S_pocket1_mol0，只做构象生成和配体准备",
        "AI4Drug",
    ),
    (
        "对接盒配置",
        "针对 EGFR（PDB: 3W2S）ATP 结合口袋 EGFR_3W2S_pocket1，帮我设置分子对接的搜索盒子",
        "AI4Drug",
    ),
    (
        "分子对接",
        "帮我把吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）对接到 EGFR（PDB: 3W2S）上，并给出对接打分",
        "AI4Drug",
    ),
    (
        "ADMET评估",
        "帮我评估吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）的 ADMET 性质",
        "AI4Drug",
    ),
    (
        "逆合成分析",
        "帮我分析一下吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）大概可以怎么合成",
        "AI4Drug",
    ),
]

PROMPTS = {
    "靶点发现": "mcporter call ai4drug.target_discovery 必须加 --timeout 600000（毫秒）；禁止 sessions_spawn。",
    "蛋白质获取": "调用 protein_acquisition，target_ids 用 EGFR_3W2S；必须传猛犸 session_id；--timeout 600000。",
    "口袋预测": "先 protein_acquisition(EGFR_3W2S) 再 pocket_prediction；禁止 sessions_spawn；--timeout 600000。",
    "分子设计": (
        "pocket_ids 必须用完整 EGFR_3W2S_pocket1；num_to_generate=3；禁止 sessions_spawn；"
        "所有 mcporter 调用 --timeout 600000（毫秒，10 分钟）。"
    ),
    "3D构象生成": "conformer_generation 必须传猛犸 session_id；molecules[].id 可用 aspirin。",
    "受体准备": "protein_acquisition + receptor_preparation，target_ids=EGFR_3W2S。",
    "配体准备": (
        "仅 conformer_generation(id=EGFR_3W2S_pocket1_mol0, SMILES 已给) + ligand_preparation；"
        "猛犸 session_id；禁止靶点发现/蛋白/口袋/对接；--timeout 600000。"
    ),
    "对接盒配置": (
        "仅 docking_box_config 或（新会话）protein_acquisition(EGFR_3W2S)+pocket_prediction+docking_box_config；"
        "pocket_ids=EGFR_3W2S_pocket1；猛犸 session_id；禁止靶点发现/受体/配体/对接；--timeout 600000。"
    ),
    "分子对接": (
        "流程 protein→receptor→pocket→box→conformer(id={pocket}_mol0)→ligand→docking；"
        "全程同一 session_id。"
    ),
    "ADMET评估": (
        "conformer_generation(gefitinib_mol0, SMILES CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl) + molecule_evaluation；"
        "猛犸 session_id；禁止联网查 SMILES；--timeout 600000。"
    ),
    "逆合成分析": (
        "先 conformer_generation（传猛犸 session_id，molecules id 如 gefitinib_mol0 + SMILES），"
        "再 retrosynthesis(molecule_ids 与构象 id 一致)。"
    ),
}


def _post_stream(payload: dict) -> tuple[str, dict[str, Any]]:
    req = urllib.request.Request(
        f"{BASE}/api/chat/stream",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    session_id = ""
    reply = ""
    error = None
    steps_seen: list[dict] = []
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        event = None
        data_lines: list[str] = []
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").rstrip("\n")
            if line.startswith("event:"):
                event = line[6:].strip()
                data_lines = []
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line == "" and event and data_lines:
                blob = "\n".join(data_lines)
                try:
                    data = json.loads(blob)
                except json.JSONDecodeError:
                    data = {}
                if event == "session":
                    session_id = str(data.get("session_id") or session_id)
                elif event == "step":
                    steps_seen.append(data)
                elif event in ("mammoth_done", "done"):
                    reply = str(data.get("reply") or reply)
                    error = data.get("error")
                    session_id = str(data.get("session_id") or session_id)
                elif event == "error":
                    error = data.get("message") or str(data)
                event = None
                data_lines = []
    return session_id, {
        "reply": reply,
        "error": error,
        "live_steps": steps_seen,
    }


def _get_process(session_id: str) -> dict:
    with urllib.request.urlopen(
        f"{BASE}/api/sessions/{session_id}/process-log", timeout=30
    ) as resp:
        return json.loads(resp.read().decode())


def _issues(skill: str, snap: dict, stream_meta: dict) -> list[str]:
    problems: list[str] = []
    if stream_meta.get("error"):
        problems.append(f"stream_error={stream_meta['error']}")
    steps = snap.get("steps") or []
    tools = [s for s in steps if s.get("kind") in ("tool", "skill", "web")]
    if not tools:
        problems.append("无工具步骤")
    for s in tools:
        title = str(s.get("title") or "")
        name = str(s.get("name") or "")
        result = str(s.get("result") or "")
        detail = str(s.get("detail") or "")
        status = str(s.get("status") or "")
        if title in ("执行命令",) or name in ("exec",):
            problems.append(f"仍显示 exec: {title}/{name}")
        if status == "running":
            problems.append(f"结束后仍 running: {title}")
        if result.strip().startswith("{") or '"success"' in result:
            problems.append(f"结果仍是 JSON: {title} → {result[:60]}")
        if "命令仍在后台运行" in result or "Process still running" in result:
            problems.append(f"工具未同步完成: {title}")
        if len(detail) > 400:
            problems.append(f"详情过长({len(detail)}): {title}")
        if "structuredContent" in detail or (detail.strip().startswith("{") and len(detail) > 120):
            problems.append(f"详情像 JSON 复读: {title}")
        if result.lstrip().startswith("#") and len(result) > 80:
            problems.append(f"结果像整份报告复读: {title}")
    reply = str(snap.get("reply") or stream_meta.get("reply") or "")
    if len(reply) < 20 and not problems:
        problems.append("回复过短")
    return problems


def run_one(name: str, message: str, category: str) -> dict[str, Any]:
    payload = {
        "message": message,
        "session_id": None,
        "selected_skill_name": name,
        "selected_skill_category": category,
        "selected_skill_system_prompt": (
            f"本轮请优先调用「{name}」对应 AI4Drug MCP 工具。\n" + PROMPTS.get(name, "")
        ),
    }
    t0 = time.time()
    try:
        sid, meta = _post_stream(payload)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:300]
        return {
            "skill": name,
            "ok": False,
            "elapsed": time.time() - t0,
            "session_id": None,
            "problems": [f"HTTP {e.code}: {body}"],
            "tools": [],
        }
    except Exception as e:
        return {
            "skill": name,
            "ok": False,
            "elapsed": time.time() - t0,
            "session_id": None,
            "problems": [f"exception: {e}"],
            "tools": [],
        }

    elapsed = time.time() - t0
    snap = {}
    if sid:
        try:
            snap = _get_process(sid)
        except Exception as e:
            return {
                "skill": name,
                "ok": False,
                "elapsed": elapsed,
                "session_id": sid,
                "problems": [f"process-log: {e}"],
                "tools": [],
            }

    problems = _issues(name, snap, meta)
    tools = [
        {
            "status": s.get("status"),
            "title": s.get("title"),
            "result": (s.get("result") or "")[:80],
        }
        for s in (snap.get("steps") or [])
        if s.get("kind") in ("tool", "skill", "web")
    ]
    return {
        "skill": name,
        "ok": not problems,
        "elapsed": elapsed,
        "session_id": sid,
        "problems": problems,
        "tools": tools,
        "agent": None,
        "reply_len": len(str(snap.get("reply") or meta.get("reply") or "")),
    }


def main() -> int:
    only = sys.argv[1:] if len(sys.argv) > 1 else []
    skills = [s for s in SKILLS if not only or s[0] in only or any(x in s[0] for x in only)]
    results = []
    print(f"Testing {len(skills)} AI4Drug skills…\n")
    for name, msg, cat in skills:
        print(f"== {name} ==", flush=True)
        print(f"prompt: {msg[:100]}", flush=True)
        r = run_one(name, msg, cat)
        results.append(r)
        status = "PASS" if r["ok"] else "FAIL"
        print(
            f"{status} sid={r['session_id']} elapsed={r['elapsed']:.0f}s "
            f"tools={len(r['tools'])} reply_len={r['reply_len']}",
            flush=True,
        )
        for t in r["tools"]:
            print(f"  [{t['status']}] {t['title']} → {t['result']}", flush=True)
        for p in r["problems"]:
            print(f"  ! {p}", flush=True)
        print(flush=True)
        # brief pause between long jobs
        time.sleep(2)

    passed = sum(1 for r in results if r["ok"])
    print("=" * 60)
    print(f"Summary: {passed}/{len(results)} passed")
    out = Path = __import__("pathlib").Path
    report = out("/tmp/ai4drug_process_test_report.json")
    report.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {report}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
