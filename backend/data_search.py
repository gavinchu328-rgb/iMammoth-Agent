"""Lightweight search proxies for AI4Drug and Huaxue data sources."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

AI4DRUG_ROOT = Path("/data2/AI4Drug")
CHEMBL_DB = AI4DRUG_ROOT / "models/chembl/chembl_37/chembl_37_sqlite/chembl_37.db"
DISEASE_MAP = AI4DRUG_ROOT / "ai4drug/resources/disease_zh_en.json"
DISEASE_LLM_CACHE = AI4DRUG_ROOT / "data/disease_zh_en_llm_cache.json"
DRUGBANK_CSV = AI4DRUG_ROOT / "models/admet_ai/admet_ai/resources/data/drugbank_approved.csv"
CHEMBL_UNIPROT = AI4DRUG_ROOT / "models/chembl/chembl_uniprot_mapping.txt"
OT_GRAPHQL = "https://api.platform.opentargets.org/api/v4/graphql"
RCSB_PDB = "https://files.rcsb.org/download/{pdb}.pdb"
RCSB_THUMB = "https://cdn.rcsb.org/images/structures/{pdb}_assembly-1.jpeg"
PUBCHEM_SDF = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/{smiles}/SDF?record_type=3d"

HUAXUE_COMPOUNDS_API = "http://127.0.0.1:3010/api/compounds"
HUAXUE_LIBRARIES_API = "http://127.0.0.1:3010/api/molecular-libraries"
REACTION_API = "http://127.0.0.1:9306/api/rxn/search"
COMPOUNDS_SEED = Path("/data1/huaxue/shared/static/compounds_seed.json")
DFT_DESCRIPTORS_CSV = Path("/data1/huixiang_db/descriptors.csv")

SOURCE_DB_MAP = {
    "reaction-pistachio": "pistachio",
    "reaction-woshi": "woshi",
    "reaction-uspto": "uspto",
    "reaction-ord": "ord",
}


def _json_load(path: Path) -> dict | list:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def search_open_targets(query: str, *, limit: int = 10) -> dict[str, Any]:
    gql = """
    query searchDisease($q: String!) {
      search(queryString: $q, entityNames: ["disease"], page: {index: 0, size: %d}) {
        hits { id name description score entity }
      }
    }
    """ % limit
    payload = json.dumps({"query": gql, "variables": {"q": query}}).encode()
    req = urllib.request.Request(
        OT_GRAPHQL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    hits = data.get("data", {}).get("search", {}).get("hits", [])
    return {"query": query, "count": len(hits), "hits": hits}


def search_chembl(gene_symbol: str, *, limit: int = 20) -> dict[str, Any]:
    if not CHEMBL_DB.exists():
        raise FileNotFoundError(f"ChEMBL database not found: {CHEMBL_DB}")
    symbol = gene_symbol.strip()
    uri = f"file:{CHEMBL_DB}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        targets = conn.execute(
            """
            SELECT DISTINCT td.tid, td.pref_name, td.chembl_id, td.organism
            FROM component_synonyms cs
            JOIN target_components tc ON cs.component_id = tc.component_id
            JOIN target_dictionary td ON tc.tid = td.tid
            WHERE UPPER(cs.component_synonym) = UPPER(?)
              AND cs.syn_type = 'GENE_SYMBOL'
            LIMIT 5
            """,
            (symbol,),
        ).fetchall()
        if not targets:
            return {"query": symbol, "count": 0, "targets": [], "compounds": []}

        tid = targets[0]["tid"]
        compounds = conn.execute(
            """
            SELECT DISTINCT md.chembl_id, md.pref_name, cs.canonical_smiles,
                   act.standard_type, act.standard_value, act.standard_units, act.pchembl_value
            FROM activities act
            JOIN assays ass ON act.assay_id = ass.assay_id
            JOIN molecule_dictionary md ON act.molregno = md.molregno
            LEFT JOIN compound_structures cs ON md.molregno = cs.molregno
            WHERE ass.tid = ?
              AND act.pchembl_value >= 5
              AND act.standard_type IN ('IC50', 'Ki', 'Kd', 'EC50')
            ORDER BY act.pchembl_value DESC
            LIMIT ?
            """,
            (tid, limit),
        ).fetchall()
        return {
            "query": symbol,
            "count": len(compounds),
            "targets": [dict(r) for r in targets],
            "compounds": [dict(r) for r in compounds],
        }
    finally:
        conn.close()


def search_disease_map(query: str) -> dict[str, Any]:
    mapping = _json_load(DISEASE_MAP)
    if not isinstance(mapping, dict):
        mapping = {}
    q = query.strip()
    exact = mapping.get(q)
    if exact:
        return {"query": q, "count": 1, "matches": [{"zh": q, "en": exact, "match_type": "exact"}]}
    partial = [
        {"zh": zh, "en": en, "match_type": "partial"}
        for zh, en in mapping.items()
        if q in zh or q in en
    ][:20]
    return {"query": q, "count": len(partial), "matches": partial}


def search_disease_llm_cache(query: str) -> dict[str, Any]:
    cache = _json_load(DISEASE_LLM_CACHE)
    if not isinstance(cache, dict):
        cache = {}
    q = query.strip()
    if q in cache:
        return {"query": q, "count": 1, "matches": [{"zh": q, "en": cache[q], "match_type": "exact"}]}
    partial = [
        {"zh": zh, "en": en, "match_type": "partial"}
        for zh, en in cache.items()
        if q in zh or q in en
    ][:20]
    return {"query": q, "count": len(partial), "matches": partial}


def search_drugbank(query: str, *, limit: int = 20) -> dict[str, Any]:
    if not DRUGBANK_CSV.exists():
        raise FileNotFoundError(f"DrugBank CSV not found: {DRUGBANK_CSV}")
    q = query.strip().lower()
    rows: list[dict[str, str]] = []
    with DRUGBANK_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").lower()
            smiles = row.get("smiles") or ""
            if q in name or q in smiles.lower():
                rows.append(dict(row))
            if len(rows) >= limit:
                break
    return {"query": query, "count": len(rows), "drugs": rows}


def search_chembl_uniprot(query: str, *, limit: int = 20) -> dict[str, Any]:
    if not CHEMBL_UNIPROT.exists():
        raise FileNotFoundError(f"ChEMBL-UniProt mapping not found: {CHEMBL_UNIPROT}")
    q = query.strip().upper()
    matches: list[dict[str, str]] = []
    with CHEMBL_UNIPROT.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.strip().split("\t")
            if len(parts) < 2:
                continue
            chembl_id, uniprot = parts[0], parts[1]
            if q in chembl_id.upper() or q in uniprot.upper():
                matches.append({"chembl_id": chembl_id, "uniprot_id": uniprot})
            if len(matches) >= limit:
                break
    return {"query": query, "count": len(matches), "mappings": matches}


def search_pdb(pdb_id: str, mirror: str = "rcsb") -> dict[str, Any]:
    pid = pdb_id.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{4}", pid):
        raise ValueError("PDB ID 应为 4 位字母数字，如 1M17")
    pdb_lower = pid.lower()
    if mirror == "pdbe":
        url = f"https://www.ebi.ac.uk/pdbe/entry-files/download/pdb{pdb_lower}.ent"
    elif mirror == "pdbj":
        url = f"https://pdbj.org/download/fetch?format=pdb&pdbid={pid}"
    else:
        url = RCSB_PDB.format(pdb=pid)
    thumb = RCSB_THUMB.format(pdb=pdb_lower)
    reachable = False
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as resp:
            reachable = resp.status < 400
    except (urllib.error.URLError, OSError):
        reachable = False
    return {
        "query": pid,
        "mirror": mirror,
        "download_url": url,
        "thumbnail_url": thumb,
        "reachable": reachable,
    }


def search_pubchem(smiles: str) -> dict[str, Any]:
    from urllib.parse import quote

    s = smiles.strip()
    url = PUBCHEM_SDF.format(smiles=quote(s, safe=""))
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            body = resp.read(2000).decode(errors="replace")
        return {"query": s, "reachable": True, "preview": body[:500], "sdf_url": url}
    except urllib.error.HTTPError as e:
        return {"query": s, "reachable": False, "error": f"HTTP {e.code}", "sdf_url": url}


def _http_get_json(url: str, *, timeout: int = 30) -> dict[str, Any] | list[Any]:
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def search_huaxue_compounds(query: str, *, limit: int = 20) -> dict[str, Any]:
    params = urllib.parse.urlencode({"keyword": query.strip(), "pageSize": limit, "page": 1})
    data = _http_get_json(f"{HUAXUE_COMPOUNDS_API}?{params}", timeout=30)
    if isinstance(data, dict):
        rows = data.get("data") or data.get("items") or []
        total = data.get("total") or len(rows)
    else:
        rows = data
        total = len(rows)
    hits = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        hits.append(
            {
                "name": row.get("title") or row.get("name"),
                "id": row.get("id") or row.get("cid"),
                "description": " | ".join(
                    str(x)
                    for x in [
                        row.get("molecularFormula") or row.get("molecular_formula"),
                        row.get("canonicalSmiles") or row.get("canonical_smiles"),
                        f"MW={row.get('molecularWeight') or row.get('molecular_weight')}",
                    ]
                    if x
                ),
                **{k: row.get(k) for k in ("inchikey", "databaseCode", "xlogp", "tpsa") if row.get(k) is not None},
            }
        )
    return {"query": query, "count": total, "hits": hits, "compounds": rows[:limit]}


def search_molecular_libraries(query: str) -> dict[str, Any]:
    data = _http_get_json(HUAXUE_LIBRARIES_API, timeout=20)
    rows = data if isinstance(data, list) else data.get("data") or []
    q = query.strip().lower()
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("databaseCode", "name", "description", "size")
        ).lower()
        if q in blob:
            matches.append(
                {
                    "name": row.get("name") or row.get("databaseCode"),
                    "id": row.get("databaseCode"),
                    "description": f"{row.get('description') or ''} · 规模 {row.get('size')} · 已导入 {row.get('compoundCount', 0)}",
                }
            )
    return {"query": query, "count": len(matches), "hits": matches, "libraries": matches}


def search_reactions(query: str, *, source_db: str | None = None, limit: int = 10) -> dict[str, Any]:
    params: dict[str, Any] = {"keyword": query.strip(), "pageSize": limit, "page": 1}
    if source_db:
        params["sourceDb"] = source_db
    url = f"{REACTION_API}?{urllib.parse.urlencode(params)}"
    data = _http_get_json(url, timeout=60)
    if not isinstance(data, dict):
        return {"query": query, "count": 0, "hits": []}
    items = data.get("items") or []
    hits = []
    for item in items:
        if not isinstance(item, dict):
            continue
        hits.append(
            {
                "id": item.get("id") or item.get("sourceId"),
                "name": item.get("canonicalRxn") or item.get("productSmiles"),
                "description": " | ".join(
                    str(x)
                    for x in [
                        f"来源={item.get('sourceDb')}",
                        f"产率={item.get('yieldValue')}",
                        (item.get("conditions") or "")[:120],
                    ]
                    if x is not None and str(x)
                ),
            }
        )
    return {
        "query": query,
        "count": data.get("total", len(hits)),
        "hits": hits,
        "reactions": items,
        "source_db": source_db,
    }


def search_compounds_seed(query: str, *, limit: int = 20) -> dict[str, Any]:
    if not COMPOUNDS_SEED.exists():
        raise FileNotFoundError(f"Seed compounds not found: {COMPOUNDS_SEED}")
    rows = json.loads(COMPOUNDS_SEED.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        rows = []
    q = query.strip().lower()
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("title", "canonical_smiles", "molecular_formula", "inchikey", "id")
        ).lower()
        if q in blob:
            matches.append(
                {
                    "name": row.get("title"),
                    "id": row.get("id"),
                    "description": f"{row.get('molecular_formula')} · {row.get('canonical_smiles')}",
                }
            )
        if len(matches) >= limit:
            break
    return {"query": query, "count": len(matches), "hits": matches}


def search_dft_descriptors(query: str, *, limit: int = 20) -> dict[str, Any]:
    if not DFT_DESCRIPTORS_CSV.exists():
        raise FileNotFoundError(f"DFT descriptors CSV not found: {DFT_DESCRIPTORS_CSV}")
    q = query.strip().lower()
    matches = []
    with DFT_DESCRIPTORS_CSV.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            mol = (row.get("mol") or "").strip()
            if not mol:
                continue
            if q in mol.lower() or q == mol.lower():
                matches.append(
                    {
                        "name": mol,
                        "id": mol,
                        "description": " | ".join(
                            f"{k}={row.get(k)}"
                            for k in ("homo_energy", "lumo_energy", "dipole", "molar_mass")
                            if row.get(k) not in (None, "")
                        ),
                    }
                )
            if len(matches) >= limit:
                break
    return {"query": query, "count": len(matches), "hits": matches}


SEARCH_HANDLERS: dict[str, Any] = {
    "open-targets-platform": search_open_targets,
    "chembl-37-sqlite": search_chembl,
    "disease-zh-en-map": search_disease_map,
    "disease-zh-en-llm-cache": search_disease_llm_cache,
    "drugbank-approved-csv": search_drugbank,
    "chembl-uniprot-mapping": search_chembl_uniprot,
    "rcsb-pdb": lambda q: search_pdb(q, "rcsb"),
    "pdbe-pdb": lambda q: search_pdb(q, "pdbe"),
    "pdbj-pdb": lambda q: search_pdb(q, "pdbj"),
    "rcsb-structure-thumbnails": lambda q: search_pdb(q, "rcsb"),
    "pubchem-pug-rest": search_pubchem,
    # Huaxue / 物质科学
    "oakclaw-compounds": search_huaxue_compounds,
    "mol-blood-exposome": search_huaxue_compounds,
    "molecular-library-registry": search_molecular_libraries,
    "unified-reactions-duckdb": search_reactions,
    "reaction-pistachio": lambda q: search_reactions(q, source_db="pistachio"),
    "reaction-woshi": lambda q: search_reactions(q, source_db="woshi"),
    "reaction-uspto": lambda q: search_reactions(q, source_db="uspto"),
    "reaction-ord": lambda q: search_reactions(q, source_db="ord"),
    "compounds-seed-json": search_compounds_seed,
    "dft-descriptors-csv": search_dft_descriptors,
}


def run_search(db_id: str, query: str) -> dict[str, Any]:
    handler = SEARCH_HANDLERS.get(db_id)
    if not handler:
        return {
            "searchable": False,
            "message": "该数据源暂不支持直接检索，请通过智能体对话查询。",
            "chat_prompt": f"请使用【{db_id}】数据源查询：{query}",
        }
    try:
        result = handler(query)
        return {"searchable": True, "result": result}
    except Exception as e:
        return {"searchable": True, "error": str(e)}
