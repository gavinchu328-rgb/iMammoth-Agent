#!/usr/bin/env python3
"""Sync Scientific Agent Skills into mammoth skills/skills.yaml for the skill plaza.

Source: /data2/scientific-agent-skills/scientific-agent-skills-main
Keeps existing mammoth/AI4Drug entries; appends all SKILL.md packages.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "skills" / "skills.yaml"
SCI_ROOT = Path("/data2/scientific-agent-skills/scientific-agent-skills-main")
SKILLS_DIR = SCI_ROOT / "skills"
DOCS = SCI_ROOT / "docs" / "skills.md"

MARKER = "  # ── Scientific Agent Skills (K-Dense)"

CATEGORY_MAP = {
    "Scientific Databases & Data Access": ("科学数据库", "🗄️"),
    "Scientific Integrations": ("平台集成", "🔌"),
    "Laboratory Information Management Systems (LIMS) & R&D Platforms": ("平台集成", "🔌"),
    "Cloud Platforms for Genomics & Biomedical Data": ("平台集成", "☁️"),
    "Laboratory Automation": ("实验室自动化", "🤖"),
    "Electronic Lab Notebooks (ELN)": ("平台集成", "📓"),
    "Workflow Platforms & Cloud Execution": ("工作流平台", "⚙️"),
    "Microscopy & Bio-image Data": ("医学影像", "🔬"),
    "Protocol Management & Sharing": ("实验室自动化", "📋"),
    "Scientific Packages": ("科研技能", "🔬"),
    "Bioinformatics & Genomics": ("生物信息学", "🧬"),
    "Data Management & Infrastructure": ("数据基础设施", "💾"),
    "Cheminformatics & Drug Discovery": ("化学信息学", "🧪"),
    "Proteomics & Mass Spectrometry": ("蛋白质组学", "🔬"),
    "Medical Imaging & Digital Pathology": ("医学影像", "🖼️"),
    "Healthcare AI & Clinical Machine Learning": ("临床研究", "🏥"),
    "Clinical Documentation & Decision Support": ("临床研究", "🏥"),
    "Neuroscience & Electrophysiology": ("神经科学", "🧠"),
    "Protein Engineering & Design": ("蛋白质工程", "🧩"),
    "Machine Learning & Deep Learning": ("机器学习", "🤖"),
    "Materials Science & Chemistry": ("材料与物理", "⚛️"),
    "Engineering & Simulation": ("工程仿真", "⚙️"),
    "Data Analysis & Visualization": ("数据分析", "📊"),
    "Phylogenetics & Evolutionary Biology": ("生物信息学", "🌳"),
    "Multi-omics & AI Agent Frameworks": ("系统生物学", "🔗"),
    "Autonomous Research & Optimization Frameworks": ("研究方法", "🎓"),
    "Scientific Communication & Publishing": ("科研写作", "📚"),
    "Document Processing & Conversion": ("文档处理", "📄"),
    "Laboratory Automation & Equipment Control": ("实验室自动化", "🤖"),
    "Tool Discovery & Computational Resources": ("基础设施", "🔧"),
    "Research Methodology & Proposal Writing": ("研究方法", "🎓"),
    "Regulatory & Standards Compliance": ("法规标准", "⚖️"),
    "Scientific Thinking & Analysis": ("研究方法", "🎓"),
    "Analysis & Methodology": ("数据分析", "📊"),
    "Decision & Scenario Analysis": ("研究方法", "🎓"),
    "Web Search & Information Retrieval": ("科研写作", "🔍"),
}

ALIASES = {
    "zarr": "zarr-python",
    "zarrpython": "zarr-python",
    "ustreasuryfiscaldata": "usfiscaldata",
    "openmmmdanalysis": "molecular-dynamics",
    "moleculardynamics": "molecular-dynamics",
    "markdownmermaidwriting": "markdown-mermaid-writing",
    "pathwayenrichment": "pathway-enrichment",
    "bulkrnaseq": "bulk-rnaseq",
    "cellxgenecensus": "cellxgene-census",
    "tiledbvcf": "tiledb-vcf",
    "iso13485certification": "iso-13485-certification",
    "piagent": "pi-agent",
    "getavailableresources": "get-available-resources",
    "optimizeforgpu": "optimize-for-gpu",
    "scientificvisualization": "scientific-visualization",
    "scientificwriting": "scientific-writing",
    "scientificslides": "scientific-slides",
    "scientificschematics": "scientific-schematics",
    "scientificbrainstorming": "scientific-brainstorming",
    "scientificcriticalthinking": "scientific-critical-thinking",
    "hypothesisgeneration": "hypothesis-generation",
    "literaturereview": "literature-review",
    "peerreview": "peer-review",
    "paperlookup": "paper-lookup",
    "citationmanagement": "citation-management",
    "researchgrants": "research-grants",
    "researchlookup": "research-lookup",
    "marketresearchreports": "market-research-reports",
    "clinicaldecisionsupport": "clinical-decision-support",
    "clinicalreports": "clinical-reports",
    "treatmentplans": "treatment-plans",
    "scholarevaluation": "scholar-evaluation",
    "whatiforacle": "what-if-oracle",
    "consciousnesscouncil": "consciousness-council",
    "dhdnaprofiler": "dhdna-profiler",
    "venuetemplates": "venue-templates",
    "latexposters": "latex-posters",
    "pptxposters": "pptx-posters",
    "generateimage": "generate-image",
    "databaselookup": "database-lookup",
    "imagingdatacommons": "imaging-data-commons",
    "huggingscience": "hugging-science",
    "opennotebook": "open-notebook",
    "ginkgocloudlab": "ginkgo-cloud-lab",
    "experimentaldesign": "experimental-design",
    "statisticalanalysis": "statistical-analysis",
    "statisticalpower": "statistical-power",
    "exploratorydataanalysis": "exploratory-data-analysis",
    "eda": "exploratory-data-analysis",
    "neuropixelsanalysis": "neuropixels-analysis",
    "timesfm": "timesfm-forecasting",
    "timesfmforecasting": "timesfm-forecasting",
    "bgptpapersearch": "bgpt-paper-search",
    "parallelweb": "parallel-web",
    "exasearch": "exa-search",
    "etetoolkit": "etetoolkit",
    "phylogenetics": "phylogenetics",
    "polarsbio": "polars-bio",
}


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower().replace("&", " and "))


def short_desc(text: str, limit: int = 90) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def q(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def main() -> int:
    if not SKILLS_DIR.is_dir():
        print(f"skills dir not found: {SKILLS_DIR}", file=sys.stderr)
        return 1

    raw = OUT.read_text(encoding="utf-8")
    if MARKER in raw:
        raw = raw.split(MARKER)[0].rstrip() + "\n"
        OUT.write_text(raw, encoding="utf-8")

    existing = yaml.safe_load(OUT.read_text(encoding="utf-8"))["skills"]

    skills_meta: dict[str, dict] = {}
    for d in sorted(SKILLS_DIR.iterdir()):
        if not d.is_dir():
            continue
        text = (d / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        fm: dict = {}
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                try:
                    fm = yaml.safe_load(text[3:end]) or {}
                except Exception:
                    fm = {}
        name = str(fm.get("name") or d.name).strip()
        desc = str(fm.get("description") or "").strip().strip('"').strip("'")
        h1 = re.search(r"^#\s+(.+)$", text, re.M)
        title = h1.group(1).strip() if h1 else name
        skills_meta[d.name] = {"id": d.name, "slug_name": name, "title": title, "description": desc}

    current_cat = "Other"
    doc_entries: list[tuple[str, str, str]] = []
    for line in DOCS.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            current_cat = line[3:].strip()
            continue
        if line.startswith("### "):
            sub = line[4:].strip()
            if sub in CATEGORY_MAP:
                current_cat = sub
            continue
        m = re.match(r"^- \*\*(.+?)\*\*\s*[-—–]\s*(.+)$", line)
        if m:
            doc_entries.append((m.group(1).strip(), m.group(2).strip(), current_cat))

    by_norm: dict[str, str] = {}
    for sid, meta in skills_meta.items():
        for key in (sid, meta["slug_name"], meta["title"]):
            by_norm[normalize(key)] = sid
        if sid.endswith("-integration"):
            by_norm[normalize(sid[:-12])] = sid
            by_norm[normalize(meta["title"].replace(" Integration", ""))] = sid

    assigned: dict[str, tuple] = {}
    for title, desc, cat in doc_entries:
        key = normalize(title)
        sid = by_norm.get(key) or ALIASES.get(key)
        if not sid:
            for k, v in by_norm.items():
                if len(key) > 5 and (key == k or key in k or k in key):
                    sid = v
                    break
        if sid in skills_meta and sid not in assigned:
            assigned[sid] = (*CATEGORY_MAP.get(cat, ("科研技能", "🔬")), desc, title)

    for sid, meta in skills_meta.items():
        if sid in assigned:
            continue
        assigned[sid] = ("科研技能", "🔬", meta["description"], meta["title"])

    existing_ids = {s["id"] for s in existing}
    sci_entries = []
    for sid in sorted(skills_meta):
        if sid in existing_ids:
            continue
        cat_cn, icon, desc, title = assigned[sid]
        meta = skills_meta[sid]
        d = desc or meta["description"] or meta["title"]
        name = title.strip()
        if not name or len(name) > 48:
            name = meta["slug_name"]
        if name == sid or (name.islower() and " " not in name):
            name = re.sub(r"[-_]", " ", name).title()
        sci_entries.append(
            {
                "id": sid,
                "name": name,
                "category": cat_cn,
                "icon": icon,
                "description": short_desc(d, 100),
                "example": f"请使用 {sid} 技能帮我：{short_desc(d, 55)}",
            }
        )

    lines = [
        "",
        MARKER + " ───────────────────────",
        f"  # 共 {len(sci_entries)} 个；id 与技能目录名一致，便于 OpenClaw 安装后调度",
        f"  # 源码: {SCI_ROOT}",
    ]
    for s in sci_entries:
        lines += [
            f"  - id: {s['id']}",
            f"    name: {q(s['name'])}",
            f"    category: {q(s['category'])}",
            f"    icon: {q(s['icon'])}",
            f"    description: {q(s['description'])}",
            f"    example: {q(s['example'])}",
            "",
        ]

    OUT.write_text(OUT.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(lines).rstrip() + "\n", encoding="utf-8")
    data = yaml.safe_load(OUT.read_text(encoding="utf-8"))
    print(f"wrote {len(sci_entries)} scientific skills; total {len(data['skills'])} -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
