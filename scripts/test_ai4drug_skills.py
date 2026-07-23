#!/usr/bin/env python3
"""Sequential smoke test for AI4Drug skill prompts via mammoth /api/chat."""
from __future__ import annotations

import json
import time
import urllib.request

API = "http://127.0.0.1:8080/api/chat"
TIMEOUT = 600

# Order mirrors pipeline; each prompt is the skill card example (with concrete IDs).
STEPS = [
    ("靶点发现", "帮我找一下肺癌的药物靶点"),
    ("蛋白质获取", "帮我获取 EGFR_3W2S 蛋白的三维结构信息"),
    ("口袋预测", "帮我预测 EGFR（PDB: 3W2S）上有哪些可能的结合口袋"),
    ("分子设计", "针对 EGFR（PDB: 3W2S）口袋 EGFR_3W2S_pocket1，帮我设计 3 个候选小分子"),
    ("3D构象生成", "帮我给阿司匹林（SMILES: CC(=O)Oc1ccccc1C(=O)O）生成三维构象"),
    ("受体准备", "帮我把 EGFR 蛋白结构（PDB: 3W2S）准备成可以做分子对接的受体"),
    (
        "配体准备",
        "帮我把吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）准备成可以做对接的配体，"
        "molecule id 用 EGFR_3W2S_pocket1_mol0",
    ),
    ("对接盒配置", "针对 EGFR（PDB: 3W2S）ATP 结合口袋 EGFR_3W2S_pocket1，帮我设置分子对接的搜索盒子"),
    (
        "分子对接",
        "帮我把吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）对接到 EGFR（PDB: 3W2S）上，并给出对接打分",
    ),
    ("ADMET评估", "帮我评估吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）的 ADMET 性质"),
    ("逆合成分析", "帮我分析一下吉非替尼（SMILES: CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl）大概可以怎么合成"),
]


def chat(message: str, session_id: str | None = None) -> dict:
    payload = {"message": message, "session_id": session_id}
    req = urllib.request.Request(
        API,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())


def ok_hint(name: str, reply: str) -> str:
    r = reply.lower()
    checks = {
        "口袋预测": ["口袋", "pocket", "p2rank", "结合"],
        "分子设计": ["分子", "smiles", "候选", "设计"],
        "受体准备": ["受体", "pdbqt", "准备"],
        "配体准备": ["配体", "pdbqt", "吉非替尼", "准备"],
        "对接盒配置": ["对接盒", "盒子", "中心", "box"],
        "分子对接": ["对接", "vina", "打分", "结合"],
        "ADMET评估": ["admet", "吸收", "毒性", "qed", "评估"],
        "逆合成分析": ["逆合成", "合成", "路线", "aizynth"],
    }
    keys = checks.get(name, [])
    hit = [k for k in keys if k in r or k in reply]
    return f"keywords={hit or ['(none)']}"


def main() -> None:
    # Seed session with target + protein so later tools have context
    print("== seed: 靶点发现 ==")
    t0 = time.time()
    res = chat("帮我找一下肺癌的药物靶点")
    sid = res["session_id"]
    print(f"session={sid} elapsed={time.time()-t0:.0f}s reply_len={len(res.get('reply') or '')}")
    print((res.get("reply") or "")[:200].replace("\n", " "))

    print("\n== seed: 蛋白质获取 ==")
    t0 = time.time()
    res = chat("帮我获取一下 EGFR 蛋白的三维结构信息", sid)
    print(f"elapsed={time.time()-t0:.0f}s reply_len={len(res.get('reply') or '')}")
    print((res.get("reply") or "")[:200].replace("\n", " "))

    results = []
    for name, prompt in STEPS:
        print(f"\n== {name} ==")
        print(f"prompt: {prompt}")
        t0 = time.time()
        try:
            res = chat(prompt, sid)
            reply = res.get("reply") or ""
            elapsed = time.time() - t0
            hint = ok_hint(name, reply)
            status = "OK" if len(reply) > 40 else "WEAK"
            print(f"{status} elapsed={elapsed:.0f}s len={len(reply)} {hint}")
            print(reply[:350].replace("\n", " "))
            results.append((name, status, elapsed, len(reply), hint))
        except Exception as e:
            elapsed = time.time() - t0
            print(f"FAIL elapsed={elapsed:.0f}s err={e}")
            results.append((name, "FAIL", elapsed, 0, str(e)))

    print("\n======== SUMMARY ========")
    for name, status, elapsed, n, hint in results:
        print(f"{status:4}  {name:8}  {elapsed:5.0f}s  len={n:5}  {hint}")


if __name__ == "__main__":
    main()
