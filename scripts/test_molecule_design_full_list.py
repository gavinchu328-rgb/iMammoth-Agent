#!/usr/bin/env python3
"""Molecule design list should include all candidates with full SMILES (no 8-line cap)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tool_summarize import _looks_like_json_leak, polish_ai4drug_exec_step


def main() -> None:
    molecules = []
    for i in range(1, 23):
        if i <= 2:
            molecules.append(
                {
                    "molecule_id": f"EGFR_3W2S_pocket1_mol{i}",
                    "smiles": "C" * 80 + str(i),
                    "source": "ai",
                }
            )
        else:
            molecules.append(
                {
                    "molecule_id": f"EGFR_3W2S_pocket1_chembl_CHEMBL{i}",
                    "smiles": "N" * 90 + str(i),
                    "chembl_id": f"CHEMBL{i}",
                    "pchembl_value": 11.0,
                    "source": "chembl",
                }
            )
    payload = {
        "success": True,
        "data": {"tool": "molecule_design", "molecules": molecules},
    }
    raw = json.dumps(payload, ensure_ascii=False)
    step = {
        "kind": "tool",
        "title": "分子设计",
        "name": "分子设计",
        "status": "done",
        "result": raw,
        "detail": raw,
    }
    polished = polish_ai4drug_exec_step(step)
    detail = polished.get("detail") or ""
    assert "22 个候选分子" in (polished.get("result") or "")
    assert detail.count("\n") + 1 >= 22, f"expected 22 lines, got {detail.count(chr(10))+1}"
    assert "mol22" in detail or "CHEMBL22" in detail, detail[-200:]
    assert "C" * 80 in detail
    assert not detail.rstrip().endswith("…"), detail[-80:]
    assert not _looks_like_json_leak(detail)
    print("ok: full molecule design list")


if __name__ == "__main__":
    main()
