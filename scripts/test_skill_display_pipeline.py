#!/usr/bin/env python3
"""Unit-test all AI4Drug skill display paths: polish → merge → stream → final summary.

Ensures each skill produces non-empty human-readable output with no JSON leak.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from reply_rebuild import (  # noqa: E402
    merge_live_steps,
    synthesize_final_from_steps,
)
from skill_display import synthesize_early_final_from_steps  # noqa: E402
from stream_content_filter import ClientStreamFilter  # noqa: E402
from tool_summarize import (  # noqa: E402
    _looks_like_json_leak,
    polish_ai4drug_exec_step,
    polish_ai4drug_exec_steps,
)

# (skill_name, tool_title, raw_json_payload, must_contain_any)
SKILL_CASES: list[tuple[str, str, dict[str, Any], tuple[str, ...]]] = [
    (
        "靶点发现",
        "靶点发现",
        {
            "success": True,
            "data": {
                "tool": "target_discovery",
                "targets": [
                    {"gene_symbol": "EGFR", "association_score": 0.912, "pdb_preview": ["3W2S"]},
                    {"gene_symbol": "ALK", "association_score": 0.801},
                ],
            },
        },
        ("EGFR", "靶点", "关联"),
    ),
    (
        "蛋白质获取",
        "蛋白质获取",
        {
            "success": True,
            "data": {
                "tool": "protein_acquisition",
                "targets": [
                    {
                        "gene_symbol": "EGFR",
                        "pdb_id": "3W2S",
                        "target_id": "EGFR_3W2S",
                        "protein": {"clean_pdb_path": "/tmp/egfr.pdb"},
                    }
                ],
            },
        },
        ("EGFR", "PDB", "3W2S"),
    ),
    (
        "口袋预测",
        "口袋预测",
        {
            "success": True,
            "data": {
                "tool": "pocket_prediction",
                "pockets": [
                    {"pocket_id": "EGFR_3W2S_pocket1", "score": 0.82, "probability": 0.91},
                ],
            },
        },
        ("pocket", "口袋", "评分"),
    ),
    (
        "分子设计",
        "分子设计",
        {
            "success": True,
            "data": {
                "tool": "molecule_design",
                "molecules": [
                    {"molecule_id": "mol1", "smiles": "CCO", "source": "ai"},
                    {"molecule_id": "mol2", "smiles": "CCN", "chembl_id": "CHEMBL25"},
                ],
            },
        },
        ("分子", "mol", "CCO"),
    ),
    (
        "3D构象生成",
        "3D构象生成",
        {
            "tool": "conformer_generation",
            "session_id": "sess-1",
            "molecules": [{"id": "EGFR_3W2S_pocket1_mol0", "smiles": "CCO", "num_conformers": 5}],
        },
        ("构象", "mol0"),
    ),
    (
        "受体准备",
        "受体准备",
        {
            "success": True,
            "data": {
                "tool": "receptor_preparation",
                "receptors": [{"target_id": "EGFR_3W2S", "pdbqt_path": "/tmp/rec.pdbqt"}],
            },
        },
        ("受体", "EGFR", "PDBQT"),
    ),
    (
        "配体准备",
        "配体准备",
        {
            "tool": "ligand_preparation",
            "session_id": "sess-1",
            "ligands": [{"molecule_id": "EGFR_3W2S_pocket1_mol0", "pdbqt_path": "/tmp/lig.pdbqt"}],
        },
        ("配体", "mol0", "PDBQT"),
    ),
    (
        "对接盒配置",
        "对接盒配置",
        {
            "success": True,
            "data": {
                "tool": "docking_box_config",
                "configs": [
                    {
                        "pocket_id": "EGFR_3W2S_pocket1",
                        "center": [10.0, 20.0, 30.0],
                        "size": [20.0, 20.0, 20.0],
                    }
                ],
            },
        },
        ("对接", "pocket", "中心"),
    ),
    (
        "分子对接",
        "分子对接",
        {
            "success": True,
            "data": {
                "tool": "molecular_docking",
                "molecules": [
                    {
                        "molecule_id": "EGFR_3W2S_pocket1_mol0",
                        "pocket_id": "EGFR_3W2S_pocket1",
                        "docking": {"score": -8.2, "pose_path": "/tmp/pose.pdbqt"},
                    }
                ],
            },
        },
        ("对接", "打分", "kcal"),
    ),
    (
        "ADMET评估",
        "ADMET 评估",
        {
            "success": True,
            "data": {
                "tool": "molecule_evaluation",
                "molecules": [
                    {
                        "molecule_id": "gefitinib_mol0",
                        "admet": {"QED": 0.72, "BBB": 0.15, "hERG": 0.31},
                    }
                ],
            },
        },
        ("ADMET", "QED", "gefitinib"),
    ),
    (
        "逆合成分析",
        "逆合成分析",
        {
            "success": True,
            "data": {
                "tool": "retrosynthesis",
                "routes": [
                    {"score": 0.88, "num_steps": 4},
                    {"score": 0.75, "steps": [{"reaction": "a"}, {"reaction": "b"}]},
                ],
            },
        },
        ("合成", "路线"),
    ),
]


def _json_leak(text: str) -> bool:
    return _looks_like_json_leak(text) or bool(re.search(r'"\w+"\s*:\s*', text) and "{" in text)


def _simulate_client_stream(step_markdown: str, final_block: str) -> str:
    """Model dumps process template then final answer; client filter keeps only final body."""
    gate = ClientStreamFilter()
    chunks = [
        "## 分析过程\n\n### 步骤 1\n",
        '{"success": true, "noise": true}',
        f"\n\n## 最终回答\n\n{final_block}",
    ]
    return "".join(gate.feed(c) for c in chunks)


def _assert_step_ui_safe(step: dict[str, Any], skill: str) -> None:
    for field in ("result", "detail"):
        val = str(step.get(field) or "")
        assert not _json_leak(val), f"{skill} step.{field} JSON leak: {val[:120]}"


def _assert_text_ok(text: str, skill: str, needles: tuple[str, ...]) -> None:
    t = (text or "").strip()
    assert t, f"{skill}: empty display text"
    assert not _json_leak(t), f"{skill}: JSON in display: {t[:160]}"
    low = t.lower()
    if not any(n.lower() in low or n in t for n in needles):
        raise AssertionError(f"{skill}: missing {needles} in {t[:200]}")


def test_skill(skill: str, title: str, payload: dict[str, Any], needles: tuple[str, ...]) -> None:
    raw = json.dumps(payload, ensure_ascii=False, indent=2)
    base_step = {
        "kind": "tool",
        "title": title,
        "name": title,
        "status": "done",
        "input": "mcporter call",
        "result": raw,
        "detail": raw,
        "tool_call_id": f"tid-{skill}",
    }
    polished = polish_ai4drug_exec_step(dict(base_step))
    _assert_step_ui_safe(polished, skill)
    block = str(polished.get("display_block") or "").strip()
    assert block, f"{skill}: missing display_block after polish"
    _assert_text_ok(block, f"{skill}/display_block", needles)

    # merge must not resurrect JSON from a longer raw update
    raw_update = {**base_step, "is_result_update": True}
    merged = merge_live_steps([polished, raw_update])
    assert len(merged) == 1
    _assert_step_ui_safe(merged[0], skill)

    steps = polish_ai4drug_exec_steps(merged)
    assert len(steps) == 1
    _assert_step_ui_safe(steps[0], skill)

    early = synthesize_early_final_from_steps(steps, skill_name=skill)
    final = synthesize_final_from_steps(steps)
    display = early or final
    _assert_text_ok(display, skill, needles)

    streamed = _simulate_client_stream("", display)
    _assert_text_ok(streamed, f"{skill}/stream", needles)
    assert '"success"' not in streamed


def main() -> int:
    failed: list[str] = []
    for skill, title, payload, needles in SKILL_CASES:
        try:
            test_skill(skill, title, payload, needles)
            print(f"PASS  {skill}")
        except AssertionError as e:
            failed.append(f"{skill}: {e}")
            print(f"FAIL  {skill}: {e}")
    print("=" * 60)
    print(f"{len(SKILL_CASES) - len(failed)}/{len(SKILL_CASES)} passed")
    if failed:
        for line in failed:
            print(f"  ! {line}")
        return 1
    print("ok: all skill display pipelines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
