#!/usr/bin/env python3
"""Tool JSON should not leak into UI-facing step fields."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tool_summarize import _looks_like_json_leak, polish_ai4drug_exec_step, polish_ai4drug_exec_steps


def main() -> None:
    huge = json.dumps(
        {
            "success": True,
            "targets": [{"gene": "EGFR", "score": 0.9}],
            "metadata": {"chembl_release": "33"},
        },
        ensure_ascii=False,
    )
    step = {
        "kind": "tool",
        "title": "靶点发现",
        "name": "靶点发现",
        "status": "done",
        "input": "糖尿病",
        "result": huge[:200],
        "detail": huge,
    }
    polished = polish_ai4drug_exec_step(step)
    assert not _looks_like_json_leak(polished.get("detail") or ""), polished.get("detail")
    assert not _looks_like_json_leak(polished.get("result") or ""), polished.get("result")
    assert polished.get("result")

    conformer = json.dumps(
        {
            "tool": "conformer_generation",
            "session_id": "sess-1",
            "molecules": [{"id": "EGFR_pocket1_mol0", "smiles": "CCO", "num_conformers": 5}],
        },
        ensure_ascii=False,
        indent=2,
    )
    ligand = json.dumps(
        {
            "tool": "ligand_preparation",
            "session_id": "sess-1",
            "ligands": [{"molecule_id": "EGFR_pocket1_mol0", "pdbqt_path": "/tmp/a.pdbqt"}],
        },
        ensure_ascii=False,
        indent=2,
    )
    for title, raw in (("3D构象生成", conformer), ("配体准备", ligand)):
        tool_step = {
            "kind": "tool",
            "title": title,
            "name": title,
            "status": "done",
            "input": "mcporter",
            "result": raw,
            "detail": raw,
        }
        p = polish_ai4drug_exec_step(tool_step)
        assert not _looks_like_json_leak(p.get("detail") or ""), (title, p.get("detail"))
        assert "mol0" in (p.get("detail") or ""), p

    steps = polish_ai4drug_exec_steps([step], reply="")
    assert not _looks_like_json_leak(steps[0].get("detail") or "")
    print("ok: tool JSON sanitized for UI")


if __name__ == "__main__":
    main()
