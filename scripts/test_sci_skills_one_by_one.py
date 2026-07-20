#!/usr/bin/env python3
"""Test scientific skills one-by-one via mammoth /api/chat.

Modes:
  default  — try install missing deps, 300s chat timeout
  --fast   — no install, 120s timeout, record issues and keep going (first pass)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

API = "http://127.0.0.1:8080/api/chat"
SKILLS_YAML = Path(__file__).resolve().parents[1] / "skills" / "skills.yaml"
RESULTS = Path("/tmp/sci_skill_test_results.jsonl")
PROGRESS = Path("/tmp/sci_skill_test_progress.json")
ENV_MAP = Path("/tmp/skill_env_map.json")
DEPS = Path("/tmp/sci_skill_deps.json")

CHAT_TIMEOUT = 300
FAST_CHAT_TIMEOUT = 120

PY_AI = "/home/dbcloud/anaconda3/envs/ai4drug/bin/python"
PIP_AI = "/home/dbcloud/anaconda3/envs/ai4drug/bin/pip"
PY_UNI = "/home/dbcloud/anaconda3/envs/unilab/bin/python"
PIP_UNI = "/home/dbcloud/anaconda3/envs/unilab/bin/pip"

PKG_IMPORT = {
    "biopython": "Bio",
    "PyTDC": "tdc",
    "pytorch-lightning": "lightning",
    "scikit-learn": "sklearn",
    "scikit-bio": "skbio",
    "scikit-survival": "sksurv",
    "python-docx": "docx",
    "python-pptx": "pptx",
    "torch-geometric": "torch_geometric",
    "stable-baselines3": "stable_baselines3",
    "umap-learn": "umap",
    "deepTools": "deeptools",
    "rowan-python": "rowan",
    "cobrapy": "cobra",
    "exa-py": "exa_py",
    "cellxgene-census": "cellxgene_census",
    "polars-bio": "polars_bio",
    "benchling-sdk": "benchling_sdk",
    "adaptyv-sdk": "adaptyv",
    "labarchives-py": "labarchives",
    "omero-py": "omero",
    "dxpy": "dxpy",
    "gprofiler-official": "gprofiler",
    "crossref-commons": "crossref_commons",
    "idc-index": "idc_index",
    "tiledbvcf-py": "tiledbvcf",
    "Pillow": "PIL",
    "fair-esm": "esm",
    "esm": "esm",
}

# Packages that need special pip install specs (not on PyPI plain name)
PKG_INSTALL_SPEC = {
    "adaptyv-sdk": "git+https://github.com/adaptyvbio/adaptyv-sdk.git",
    "benchling-sdk": "benchling-sdk",
    "deepTools": "deeptools",
    "rowan-python": "rowan-python",
    "esm": "fair-esm",
}

# Skip these optional/system/binary deps during auto-install
SKIP_INSTALL = {
    "fastp", "fastqc", "fasttree", "iqtree", "mafft", "salmon", "star",
    "subread", "trim-galore", "multiqc", "nextflow", "nf-core",
    "bids-validator-deno", "gdal", "postgis", "spatialite", "mkl",
    "dev", "flash-attn",
}


def load_sci_skills() -> list[dict]:
    data = yaml.safe_load(SKILLS_YAML.read_text(encoding="utf-8"))
    orig_ids = {s["id"] for s in data["skills"][:25]}
    return [s for s in data["skills"] if s["id"] not in orig_ids]


def load_progress() -> dict:
    if PROGRESS.exists():
        return json.loads(PROGRESS.read_text())
    return {"done": {}, "last_index": -1}


def save_progress(prog: dict) -> None:
    PROGRESS.write_text(json.dumps(prog, ensure_ascii=False, indent=2))


def pkg_import(pkg: str) -> str:
    if pkg in PKG_IMPORT:
        return PKG_IMPORT[pkg]
    return pkg.replace("-", "_").lower()


def skill_packages(skill_id: str) -> list[str]:
    if not DEPS.exists():
        return []
    for d in json.loads(DEPS.read_text()):
        if d["id"] == skill_id:
            return d.get("packages") or []
    return []


def skill_env(skill_id: str) -> str:
    if ENV_MAP.exists():
        m = json.loads(ENV_MAP.read_text())
        return m.get(skill_id, "ai4drug")
    return "ai4drug"


def import_ok(py: str, pkg: str) -> bool:
    mod = pkg_import(pkg)
    code = f"import importlib; importlib.import_module({mod!r})"
    r = subprocess.run([py, "-c", code], capture_output=True, timeout=60)
    return r.returncode == 0


def install_packages(pip: str, pkgs: list[str]) -> tuple[bool, str]:
    if not pkgs:
        return True, "no packages"
    specs = []
    skipped = []
    for p in pkgs:
        if p in SKIP_INSTALL:
            skipped.append(p)
            continue
        specs.append(PKG_INSTALL_SPEC.get(p, p))
    msgs = []
    if skipped:
        msgs.append(f"skipped binary/optional: {skipped}")
    if not specs:
        return True, "; ".join(msgs) or "nothing to install"
    # install one-by-one so one failure doesn't block others
    failed = []
    for spec in specs:
        cmd = [pip, "install", "-q", spec]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            failed.append(f"{spec}:{(r.stderr or r.stdout or '')[-200:]}")
    if failed:
        msgs.append("failed: " + " | ".join(failed[:3]))
        return False, "; ".join(msgs)
    msgs.append(f"installed {specs}")
    return True, "; ".join(msgs)


def chat(prompt: str, timeout: int = 300) -> tuple[str, str, int]:
    payload = json.dumps({"message": prompt, "session_id": None}).encode()
    req = urllib.request.Request(
        API,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        reply = data.get("reply") or ""
        elapsed = int(time.time() - t0)
        if len(reply) < 30:
            return "WEAK", reply[:200], elapsed
        # Only treat clear import failures as IMPORT_ERR (not soft mentions of pip)
        if re.search(r"(ModuleNotFoundError|No module named ['\"]?\w+['\"]?)", reply):
            return "IMPORT_ERR", reply[:400], elapsed
        return "OK", reply[:400], elapsed
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        return "HTTP_ERR", f"{e.code}: {body}", int(time.time() - t0)
    except Exception as e:
        return "FAIL", str(e)[:300], int(time.time() - t0)


def ensure_deps(skill_id: str, *, fast: bool = False) -> tuple[bool, str]:
    env = skill_env(skill_id)
    py = PY_UNI if env == "unilab" else PY_AI
    pip = PIP_UNI if env == "unilab" else PIP_AI
    pkgs = skill_packages(skill_id)
    if not pkgs:
        return True, "no pip deps"
    missing = [p for p in pkgs if not import_ok(py, p)]
    if not missing:
        return True, f"all {len(pkgs)} pkgs ok"
    if fast:
        return False, f"missing (fast skip install): {missing[:5]}{'...' if len(missing) > 5 else ''}"
    ok, out = install_packages(pip, missing)
    still = [p for p in missing if not import_ok(py, p)]
    if still:
        return False, f"install failed, still missing: {still[:5]} | {out}"
    return True, f"installed {missing}"


def log_result(row: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--fast"]
    fast = "--fast" in sys.argv or os.environ.get("SKILL_TEST_FAST") == "1"
    start = int(args[0]) if len(args) > 0 else 0
    limit = int(args[1]) if len(args) > 1 else 9999
    chat_timeout = FAST_CHAT_TIMEOUT if fast else CHAT_TIMEOUT

    skills = load_sci_skills()
    prog = load_progress()

    end = min(len(skills), start + limit)
    mode = "FAST (skip install, short timeout)" if fast else "FULL"
    print(f"Testing skills [{start}:{end}) of {len(skills)} — {mode}", flush=True)

    for i in range(start, end):
        s = skills[i]
        sid = s["id"]
        prev = prog["done"].get(sid)
        if prev and prev.get("status") == "OK":
            print(f"[{i+1}/{len(skills)}] SKIP {sid} (already OK)", flush=True)
            continue
        if fast and prev and prev.get("pass") == "fast":
            print(f"[{i+1}/{len(skills)}] SKIP {sid} (fast pass done)", flush=True)
            continue

        print(f"\n[{i+1}/{len(skills)}] === {sid} ===", flush=True)
        dep_ok, dep_msg = ensure_deps(sid, fast=fast)
        print(f"  deps: {dep_msg}", flush=True)

        status, snippet, elapsed = chat(s["example"], timeout=chat_timeout)
        # Normalize timeout / import issues as SKIP for first pass
        if fast and status in ("FAIL", "HTTP_ERR") and "timed out" in snippet.lower():
            status = "SKIP"
        if fast and status == "IMPORT_ERR":
            status = "SKIP"
        if fast and not dep_ok:
            status = "SKIP" if status != "OK" else status

        print(f"  result: {status} ({elapsed}s) {snippet[:120].replace(chr(10),' ')}...", flush=True)

        row = {
            "index": i,
            "id": sid,
            "status": status,
            "deps_ok": dep_ok,
            "deps_msg": dep_msg,
            "elapsed": elapsed,
            "snippet": snippet,
            "example": s["example"][:120],
            "pass": "fast" if fast else "full",
        }
        log_result(row)
        prog["done"][sid] = row
        prog["last_index"] = i
        save_progress(prog)

    counts: dict[str, int] = {}
    for v in prog["done"].values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    print("\n=== SUMMARY ===", counts, flush=True)
    if fast:
        skip = [k for k, v in prog["done"].items() if v.get("status") in ("SKIP", "FAIL", "IMPORT_ERR", "HTTP_ERR", "WEAK")]
        print(f"Needs follow-up: {len(skip)} skills -> /tmp/sci_skill_test_needs_fix.txt", flush=True)
        Path("/tmp/sci_skill_test_needs_fix.txt").write_text("\n".join(sorted(skip)) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
