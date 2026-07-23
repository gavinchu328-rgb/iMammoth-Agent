"""把 OpenClaw 原始工具调用整理成友好的中文摘要（不暴露完整路径）。"""

from __future__ import annotations

import json
import re
from typing import Any

_PATH_RE = re.compile(
    r"(?:~|/home/|/data\d?/|/tmp/|\.\/)[^\s\"']+",
)
_SKILL_MD_RE = re.compile(
    r"(?:skills|skill)[/\\]([^/\\]+)[/\\]SKILL\.md",
    re.I,
)
_CHEM_CALC_RE = re.compile(
    r"chemistry-calc\s+(\w+)\s+[\"']?([^\s\"']+)",
    re.I,
)
_PDB_ID_RE = re.compile(r"\b([1-9][A-Za-z0-9]{3})\b")
_RCSB_SEARCH_RE = re.compile(r"search\.rcsb\.org/rcsbsearch", re.I)
_RCSB_GRAPHQL_RE = re.compile(r"data\.rcsb\.org/graphql", re.I)
_RCSB_ENTRY_RE = re.compile(r"data\.rcsb\.org/rest/v1/core/entry/([1-9A-Za-z0-9]{4})", re.I)
_RCSB_DOWNLOAD_RE = re.compile(r"files\.rcsb\.org/download/([1-9A-Za-z0-9]{4})", re.I)
_MAMMOTH_PDB_API_RE = re.compile(r"/api/databases/(?:rcsb-pdb|pdbe-pdb|pdbj-pdb)", re.I)
_MAMMOTH_PDB_TEXT_API_RE = re.compile(r"/api/databases/rcsb-pdb-text/search", re.I)
_MAMMOTH_PDB_META_API_RE = re.compile(r"/api/databases/rcsb-pdb-metadata/search", re.I)
_MCPORTER_AI4DRUG_RE = re.compile(
    r"mcporter\s+call\s+ai4drug\.([a-z0-9_]+)",
    re.I,
)

_SKILL_DISPLAY: dict[str, str] = {
    "database-lookup": "科学数据库查询",
    "pdb-text-search": "PDB 文本搜索",
    "pdb-metadata-lookup": "PDB 元数据查询",
    "pdb-structure-download": "PDB 结构下载",
    "chemistry-calculation": "化学计算",
    "chemical_reaction": "化学智能中心",
    "ai4drug-target-discovery": "靶点发现",
}


def strip_paths(text: str) -> str:
    """隐藏绝对路径，保留文件名或技能名。"""
    s = text or ""

    def repl(m: re.Match[str]) -> str:
        p = m.group(0)
        skill = _SKILL_MD_RE.search(p)
        if skill:
            return f"技能「{skill.group(1)}」"
        base = p.rstrip("/").split("/")[-1]
        return base or "文件"

    return _PATH_RE.sub(repl, s)


def _skill_display_name(skill_id: str) -> str:
    sid = (skill_id or "").strip()
    return _SKILL_DISPLAY.get(sid, sid.replace("-", " ").replace("_", " "))


def _extract_json_blob(text: str) -> Any | None:
    text = (text or "").strip()
    if not text:
        return None
    for candidate in (text, text[text.find("{") :] if "{" in text else ""):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _is_valid_pdb_id(pid: str) -> bool:
    token = (pid or "").strip().upper()
    if len(token) != 4:
        return False
    if token in ("HTTP", "JSON", "POST", "GET"):
        return False
    # 排除纯数字（如端口 8080），PDB ID 通常含字母
    return any(ch.isalpha() for ch in token)


def _extract_search_query_from_cmd(cmd: str) -> str:
    data = _extract_json_blob(cmd)
    if isinstance(data, dict):
        q = data.get("query")
        if isinstance(q, str) and q.strip():
            return q.strip()[:120]
        if isinstance(q, dict):
            params = q.get("parameters") or {}
            for key in ("value", "attribute", "text"):
                if params.get(key):
                    return str(params[key])[:120]
        for key in ("text", "query", "q", "keyword"):
            if data.get(key):
                return str(data[key])[:120]
    m = re.search(r'"value"\s*:\s*"([^"]{2,120})"', cmd)
    if m:
        return m.group(1)
    m = re.search(r'query[=:]\s*["\']?([^"\'&\s]{2,80})', cmd, re.I)
    if m:
        return m.group(1)
    return ""


def _extract_pdb_id_from_cmd(cmd: str) -> str:
    data = _extract_json_blob(cmd)
    if isinstance(data, dict):
        for key in ("query", "pdb_id"):
            val = data.get(key)
            if isinstance(val, str) and _is_valid_pdb_id(val):
                return val.strip().upper()[:4]
    m = _RCSB_ENTRY_RE.search(cmd) or _RCSB_DOWNLOAD_RE.search(cmd)
    if m:
        return m.group(1).upper()
    ids = _PDB_ID_RE.findall(cmd)
    for pid in ids:
        if _is_valid_pdb_id(pid):
            return pid.upper()
    return ""


def _friendly_pdb_exec(cmd: str) -> tuple[str, str, str] | None:
    c = cmd or ""
    cl = c.lower()
    if _MAMMOTH_PDB_TEXT_API_RE.search(c):
        q = _extract_search_query_from_cmd(c)
        return ("PDB 文本搜索", "PDB 文本搜索", q or "关键词搜索")
    if _MAMMOTH_PDB_META_API_RE.search(c):
        pid = _extract_pdb_id_from_cmd(c) or _extract_search_query_from_cmd(c)
        return ("PDB 元数据查询", "PDB 元数据查询", pid or "按 PDB ID 查询")
    if _RCSB_SEARCH_RE.search(c) or "rcsbsearch" in cl:
        q = _extract_search_query_from_cmd(c)
        return ("PDB 文本搜索", "PDB 文本搜索", q or "关键词搜索")
    if _RCSB_GRAPHQL_RE.search(c) or _RCSB_ENTRY_RE.search(c):
        pid = _extract_pdb_id_from_cmd(c)
        return ("PDB 元数据查询", "PDB 元数据查询", pid or "按 PDB ID 查询")
    if _RCSB_DOWNLOAD_RE.search(c) or _MAMMOTH_PDB_API_RE.search(c):
        pid = _extract_pdb_id_from_cmd(c)
        q = _extract_search_query_from_cmd(c) if not pid else pid
        return ("PDB 结构下载", "PDB 结构下载", q or "下载结构文件")
    if "references/pdb.md" in cl or "database-lookup" in cl:
        if "rcsbsearch" in cl or "text" in cl and "search.rcsb" in cl:
            return ("PDB 文本搜索", "PDB 文本搜索", _extract_search_query_from_cmd(c) or "PDB 检索")
        if "core/entry" in cl or "graphql" in cl:
            return ("PDB 元数据查询", "PDB 元数据查询", _extract_pdb_id_from_cmd(c) or "元数据")
        if "files.rcsb.org" in cl or "download" in cl:
            return ("PDB 结构下载", "PDB 结构下载", _extract_pdb_id_from_cmd(c) or "下载")
    return None


_WEB_SEARCH_TOOLS = frozenset(
    {
        "web_search",
        "web_fetch",
        "websearch",
        "webfetch",
        "brave_web_search",
        "brave_search",
        "tavily_search",
        "tavily",
        "exa_search",
        "exa",
        "exa-search",
        "desearch-web-search",
        "desearch_web_search",
        "desearch",
        "parallel_web",
        "parallel-web",
        "parallel_web_search",
    }
)

_WEB_TOOL_LABELS: dict[str, str] = {
    "web_search": "网络搜索",
    "websearch": "网络搜索",
    "web_fetch": "网页抓取",
    "webfetch": "网页抓取",
    "brave_web_search": "Brave 搜索",
    "brave_search": "Brave 搜索",
    "tavily_search": "Tavily 搜索",
    "tavily": "Tavily 搜索",
    "exa_search": "Exa 搜索",
    "exa": "Exa 搜索",
    "desearch_web_search": "Desearch 搜索",
    "desearch": "Desearch 搜索",
    "parallel_web": "Parallel 搜索",
    "parallel_web_search": "Parallel 搜索",
}


def _web_tool_label(tool_name: str) -> str:
    base = (tool_name or "").strip().lower().replace("-", "_")
    if base in _WEB_TOOL_LABELS:
        return _WEB_TOOL_LABELS[base]
    for key, label in _WEB_TOOL_LABELS.items():
        if key in base:
            return label
    if "fetch" in base:
        return "网页抓取"
    if any(k in base for k in ("search", "tavily", "brave", "exa", "desearch")):
        return "网络搜索"
    return "网络工具"


def _friendly_web_tool(tool_name: str, arguments: dict) -> tuple[str, str, str, str] | None:
    name = (tool_name or "").strip().lower().replace("-", "_")
    base = name.replace("__", "_")
    if base not in _WEB_SEARCH_TOOLS and not any(
        k in base for k in ("web_search", "web_fetch", "websearch", "webfetch", "brave", "tavily", "exa", "desearch", "parallel_web")
    ):
        return None
    args = arguments if isinstance(arguments, dict) else {}
    query = ""
    for key in ("query", "q", "url", "text", "prompt"):
        if args.get(key):
            query = str(args[key])[:120]
            break
    label = _web_tool_label(tool_name)
    title = f"{label}工具"
    inp = query or ("抓取网页" if "抓取" in label else "检索互联网")
    return (title, label, inp, "tool")


def _summarize_web_search(raw: str, tool_name: str) -> dict[str, str] | None:
    text = (raw or "").strip()
    if not text:
        return None
    if "database_id" in text and ("rcsb-pdb" in text or "download_url" in text):
        return None
    data = _extract_json_blob(text)
    if isinstance(data, dict):
        if data.get("status") == "error" or data.get("isError"):
            err = str(data.get("error") or data.get("message") or "搜索失败")[:160]
            return {"result": "搜索未完成", "detail": err}
        results = data.get("results") or data.get("organic") or data.get("items")
        if isinstance(results, list):
            n = len(results)
            bits = []
            for row in results[:5]:
                if not isinstance(row, dict):
                    continue
                title = (row.get("title") or row.get("name") or "")[:80]
                url = row.get("url") or row.get("link") or ""
                if title:
                    bits.append(f"{title}" + (f" ({url})" if url else ""))
            summary = f"返回 {n} 条结果"
            return {"result": summary, "detail": "\n".join(bits) if bits else summary}
    if "exceeds your plan" in text.lower():
        return {"result": "搜索未完成", "detail": strip_paths(text)[:300]}
    cleaned = strip_paths(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    label = "网页抓取" if "fetch" in (tool_name or "").lower() else "网络搜索"
    summary = cleaned[:120] + ("…" if len(cleaned) > 120 else "")
    return {"result": f"{label}完成", "detail": summary or "执行完成"}


def _is_web_tool(tool_name: str) -> bool:
    base = (tool_name or "").strip().lower().replace("-", "_")
    if base in _WEB_SEARCH_TOOLS:
        return True
    return any(
        k in base
        for k in ("web_search", "web_fetch", "websearch", "webfetch", "brave", "tavily", "exa", "desearch", "parallel_web")
    )


def _is_exec_tool(tool_name: str) -> bool:
    return (tool_name or "").strip().lower() in ("exec", "bash", "shell")


def _summarize_exec_output(text: str) -> dict[str, str] | None:
    """Summarize shell/exec output without mislabeling as web search."""
    raw = (text or "").strip()
    if not raw:
        return None

    # mcporter / AI4Drug MCP via exec：按结果 JSON 推断并摘要
    ai4 = _summarize_ai4drug_structured("exec", raw)
    if ai4:
        return ai4

    fail_patterns = (
        (re.compile(r"curl:\s*\(\d+\)", re.I), "命令执行失败"),
        (re.compile(r"workdir.*unavailable", re.I), "工作目录不可用"),
        (re.compile(r"command was not executed", re.I), "命令未执行"),
        (re.compile(r"Exec failed", re.I), "执行失败"),
        (re.compile(r"timed out", re.I), "执行超时"),
        (re.compile(r"appears offline", re.I), "MCP 服务离线"),
        (re.compile(r"validation error", re.I), "参数校验失败"),
        (re.compile(r"Command still running", re.I), "命令仍在后台运行"),
    )
    for pat, label in fail_patterns:
        if pat.search(raw):
            return {"result": label, "detail": _clip_detail(strip_paths(raw), max_chars=200)}

    data = _extract_json_blob(raw)
    if isinstance(data, dict):
        if data.get("error") and data.get("database_id"):
            err = str(data.get("error") or data.get("message") or "接口错误")
            return {"result": "接口调用失败", "detail": err[:300]}
        if data.get("status") == 404 and data.get("message"):
            return {"result": "RCSB 未找到数据", "detail": str(data["message"])[:300]}
        if "rcsb_entry_info" in data or data.get("entry"):
            return _summarize_rcsb_entry(data)
        reflns = data.get("reflns")
        if isinstance(reflns, dict) and reflns.get("d_resolution_high") is not None:
            res = reflns["d_resolution_high"]
            return {"result": f"分辨率 {res} Å", "detail": strip_paths(raw)[:500]}
        # 勿把整段 JSON 当详情
        if "success" in data or data.get("tool") in _AI4DRUG_SHORT_NAMES:
            return {"result": "工具执行完成", "detail": ""}

    if re.search(r"\b[1-9][A-Z0-9]{3}\b:\s*resolution=", raw, re.I):
        lines = [ln.strip() for ln in re.split(r"\s{2,}|\n", raw) if re.search(r"resolution=", ln, re.I)]
        if lines:
            return {"result": f"已获取 {len(lines)} 条分辨率", "detail": "\n".join(lines[:12])}

    if re.search(r"\b[1-9][A-Z0-9]{3}\b.*N/A\s*Å", raw):
        return {"result": "未解析到分辨率", "detail": strip_paths(raw)[:500]}

    if "data.rcsb.org" in raw.lower() or raw.startswith("{") and ("audit_author" in raw or "reflns" in raw):
        if isinstance(data, dict):
            return _summarize_rcsb_entry(data)

    return None


def _friendly_read(arguments: dict) -> tuple[str, str, str, str]:
    path = str(arguments.get("path") or arguments.get("file") or "")
    skill = _SKILL_MD_RE.search(path)
    if skill:
        sid = skill.group(1)
        label = _skill_display_name(sid)
        return (
            f"执行技能「{label}」",
            label,
            "加载技能说明与调用规范",
            "skill",
        )
    name = path.rstrip("/").split("/")[-1] if path else "文件"
    return (f"读取「{name}」", "read", f"读取 {name}", "tool")


def _friendly_exec(arguments: dict) -> tuple[str, str, str, str]:
    cmd = str(arguments.get("command") or "")
    mcp = _parse_mcporter_ai4drug(cmd)
    if mcp:
        title, name, inp = mcp
        return (title, name, inp, "tool")
    chem = _CHEM_CALC_RE.search(cmd)
    if chem:
        action, arg = chem.group(1), chem.group(2)
        if action.lower() == "properties":
            return (
                "化学性质计算",
                "chemistry-calculation (properties)",
                f'SMILES "{arg}"，查询分子量',
                "tool",
            )
        return (
            f"化学计算 · {action}",
            f"chemistry-calculation ({action})",
            f'输入 "{arg}"',
            "tool",
        )
    pdb = _friendly_pdb_exec(cmd)
    if pdb:
        title, name, inp = pdb
        return (title, name, inp, "tool")
    # 读取报告 / cat markdown：不当成裸 exec
    if "ai4drug-reports" in cmd or re.search(r"\bcat\b.*\.md\b", cmd):
        return ("读取报告", "读取报告", "AI4Drug 报告", "tool")
    cleaned = strip_paths(cmd)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > 80:
        cleaned = cleaned[:77] + "…"
    return ("执行命令", "exec", cleaned or "执行操作", "tool")


def _friendly_generic(name: str, arguments: Any) -> tuple[str, str, str, str]:
    if isinstance(arguments, dict):
        for key in ("query", "q", "text", "prompt", "smiles", "formula", "url", "name"):
            if key in arguments and arguments[key]:
                val = str(arguments[key])[:120]
                return (name, name, strip_paths(val), "tool")
        blob = strip_paths(json.dumps(arguments, ensure_ascii=False))[:120]
        return (name, name, blob, "tool")
    return (name, name, strip_paths(str(arguments))[:120], "tool")


_AI4DRUG_TOOL_LABELS: dict[str, str] = {
    "ai4drug__target_discovery": "靶点发现",
    "ai4drug__protein_acquisition": "蛋白质获取",
    "ai4drug__pocket_prediction": "口袋预测",
    "ai4drug__molecule_design": "分子设计",
    "ai4drug__conformer_generation": "3D构象生成",
    "ai4drug__receptor_preparation": "受体准备",
    "ai4drug__ligand_preparation": "配体准备",
    "ai4drug__docking_box_config": "对接盒配置",
    "ai4drug__molecular_docking": "分子对接",
    "ai4drug__molecule_evaluation": "ADMET 评估",
    "ai4drug__retrosynthesis": "逆合成分析",
    "ai4drug__pipeline_summary": "流程汇总",
}

_AI4DRUG_SHORT_NAMES: dict[str, str] = {
    k.replace("ai4drug__", ""): v for k, v in _AI4DRUG_TOOL_LABELS.items()
}


def _ai4drug_label_from_short(short: str) -> str:
    key = (short or "").strip().lower()
    return _AI4DRUG_SHORT_NAMES.get(key) or key.replace("_", " ")


def _parse_mcporter_ai4drug(cmd: str) -> tuple[str, str, str] | None:
    """Parse `mcporter call ai4drug.xxx ...` → (title, name, input)."""
    m = _MCPORTER_AI4DRUG_RE.search(cmd or "")
    if not m:
        return None
    short = m.group(1).lower()
    label = _ai4drug_label_from_short(short)
    parts: list[str] = []
    for key in (
        "target_ids",
        "molecule_ids",
        "pocket_ids",
        "disease_name",
        "disease",
    ):
        km = re.search(
            rf"""{key}\s*=\s*(?:'([^']*)'|"([^"]*)"|(\[[^\]]*\]|[^\s]+))""",
            cmd,
        )
        if not km:
            continue
        val = next((g for g in km.groups() if g is not None), "").strip()
        if val:
            parts.append(strip_paths(val)[:80])
    if re.search(r"\bmolecules\s*=", cmd):
        parts.append("分子构象")
    inp = " · ".join(parts) if parts else "执行中"
    return (label, label, inp)


_HUAXUE_AI_CURL_LABELS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/api/ai/reaction-predict\b", re.I), "反应预测"),
    (re.compile(r"/api/ai/retrosynthesis\b", re.I), "逆合成分析"),
    (re.compile(r"/api/ai/catalyst-predict\b", re.I), "催化剂推荐"),
    (re.compile(r"/api/ai/virtual-screen\b", re.I), "虚拟筛选"),
    (re.compile(r"/api/ai/generate/molecule\b", re.I), "分子生成"),
    (re.compile(r"/api/ai/predict/property\b", re.I), "性质预测"),
    (re.compile(r"/api/ai/explain/property\b", re.I), "性质解释"),
    (re.compile(r"/api/ai/agent-chat\b", re.I), "化学智能对话"),
    (re.compile(r"/api/chem/standardize\b", re.I), "SMILES 标准化"),
    (re.compile(r"/api/chem/calculate\b", re.I), "分子性质计算"),
    (re.compile(r"/api/chem/lipinski\b", re.I), "Lipinski 评估"),
    (re.compile(r"/api/chem/fingerprint\b", re.I), "分子指纹"),
)


def _parse_huaxue_ai_curl(cmd: str) -> tuple[str, str, str] | None:
    """Parse chemical_reaction curl to :3010 → friendly (title, name, input)."""
    text = cmd or ""
    if "3010" not in text and "/api/ai/" not in text and "/api/chem/" not in text:
        return None
    if "curl" not in text.lower() and "http" not in text.lower():
        return None
    for pat, label in _HUAXUE_AI_CURL_LABELS:
        if pat.search(text):
            return (label, label, "化学智能中心")
    if re.search(r":3010/api/(?:ai|chem)/", text, re.I):
        return ("化学智能中心", "化学智能中心", "执行中")
    return None


def _infer_ai4drug_tool_key(data: dict[str, Any]) -> str:
    """Infer ai4drug__xxx from result JSON when tool_name is exec."""
    tool = str(data.get("tool") or "").strip().lower()
    if tool in _AI4DRUG_SHORT_NAMES:
        return f"ai4drug__{tool}"
    inner = data.get("data") if isinstance(data.get("data"), dict) else data
    if not isinstance(inner, dict):
        return ""
    if inner.get("receptors"):
        return "ai4drug__receptor_preparation"
    if inner.get("targets") and (inner.get("session_id") or data.get("success") is not None):
        # protein vs target_discovery: protein has pdb_id / clean_pdb
        sample = (inner.get("targets") or [None])[0]
        if isinstance(sample, dict) and (
            sample.get("pdb_id") or sample.get("protein") or sample.get("clean_pdb_path")
        ):
            return "ai4drug__protein_acquisition"
        if isinstance(sample, dict) and sample.get("receptor_path"):
            return "ai4drug__receptor_preparation"
        if isinstance(sample, dict) and (
            sample.get("association_score") is not None or sample.get("gene_symbol")
        ):
            return "ai4drug__target_discovery"
        return "ai4drug__protein_acquisition"
    if inner.get("pockets"):
        return "ai4drug__pocket_prediction"
    if inner.get("configs") or inner.get("docking_boxes") or inner.get("boxes"):
        return "ai4drug__docking_box_config"
    if inner.get("ligands") and not inner.get("molecules"):
        return "ai4drug__ligand_preparation"
    # ADMET 优先：molecules[].admet 存在即可（docking 可能为 null）
    if (
        isinstance(inner.get("molecules"), list)
        and inner.get("molecules")
        and isinstance(inner["molecules"][0], dict)
        and isinstance(inner["molecules"][0].get("admet"), dict)
    ):
        return "ai4drug__molecule_evaluation"
    if inner.get("evaluations"):
        return "ai4drug__molecule_evaluation"
    if inner.get("docking_results") or (
        isinstance(inner.get("molecules"), list)
        and inner.get("molecules")
        and isinstance(inner["molecules"][0], dict)
        and isinstance(inner["molecules"][0].get("docking"), dict)
    ):
        return "ai4drug__molecular_docking"
    if inner.get("routes") or inner.get("synthesis_routes"):
        return "ai4drug__retrosynthesis"
    if inner.get("molecules") or data.get("tool") == "conformer_generation":
        # design vs conformer: design often has source/chembl
        mols = inner.get("molecules") or []
        if isinstance(mols, list) and mols and isinstance(mols[0], dict):
            if isinstance(mols[0].get("admet"), dict):
                return "ai4drug__molecule_evaluation"
            if isinstance(mols[0].get("docking"), dict):
                return "ai4drug__molecular_docking"
            if mols[0].get("source") or mols[0].get("chembl_id"):
                return "ai4drug__molecule_design"
        if data.get("tool") == "conformer_generation" or "conformer" in str(
            data.get("description") or ""
        ):
            return "ai4drug__conformer_generation"
        return "ai4drug__molecule_design"
    if inner.get("report_id") or inner.get("pipeline"):
        return "ai4drug__pipeline_summary"
    return ""


def _friendly_ai4drug(tool_name: str, arguments: dict) -> tuple[str, str, str] | None:
    label = _AI4DRUG_TOOL_LABELS.get(tool_name)
    if not label and tool_name.startswith("ai4drug__"):
        label = tool_name.replace("ai4drug__", "").replace("_", " ")
    if not label:
        return None
    parts: list[str] = []
    for key in ("disease_name", "disease", "target_ids", "molecule_ids", "molecules", "pocket_ids"):
        if key not in arguments or arguments[key] in (None, "", [], {}):
            continue
        val = arguments[key]
        if isinstance(val, list) and val and isinstance(val[0], dict):
            parts.append(f"{len(val)} 个分子")
        else:
            parts.append(strip_paths(str(val))[:100])
    inp = " · ".join(parts) if parts else "执行中"
    return (label, label, inp)


def _unwrap_tool_result_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Unwrap mammoth /api/databases/*/search responses: { result: {...} }."""
    inner = data.get("result")
    if isinstance(inner, dict):
        if any(
            key in inner
            for key in (
                "total_count",
                "result_set",
                "resultSet",
                "hits",
                "pdb_id",
                "download_url",
                "rcsb_entry_info",
                "entry",
                "ligands",
            )
        ):
            return inner
    return data


def _summarize_mammoth_pdb_metadata(data: dict[str, Any]) -> dict[str, str]:
    pid = str(data.get("pdb_id") or "").upper()
    title = (data.get("title") or "").strip()
    resolution = data.get("resolution")
    method = data.get("experimental_method") or ""
    release = data.get("release_date") or ""
    bits: list[str] = []
    if pid:
        bits.append(f"PDB {pid}")
    if resolution is not None:
        if isinstance(resolution, list) and resolution:
            bits.append(f"分辨率 {resolution[0]} Å")
        else:
            bits.append(f"分辨率 {resolution} Å")
    if method:
        bits.append(str(method))
    if release:
        bits.append(f"发布 {str(release)[:10]}")
    summary = " · ".join(bits) if bits else "已获取元数据"
    lines = [summary]
    if title:
        lines.append(title[:200])
    ligands = data.get("ligands") or []
    if isinstance(ligands, list) and ligands:
        lig_lines: list[str] = []
        for row in ligands[:8]:
            if not isinstance(row, dict):
                continue
            comp = str(row.get("chem_comp_id") or "").strip()
            name = str(row.get("name") or "").strip()
            eid = str(row.get("entity_id") or "").strip()
            if comp and name:
                lig_lines.append(f"{comp} ({name})" + (f", entity {eid}" if eid else ""))
            elif comp:
                lig_lines.append(comp)
            elif name:
                lig_lines.append(name)
        if lig_lines:
            lines.append("配体: " + "; ".join(lig_lines))
    else:
        legacy = data.get("ligand_entity_ids") or []
        if legacy:
            lines.append("配体实体: " + ", ".join(str(x) for x in legacy[:8]))
    return {"result": summary, "detail": "\n".join(lines)}


def _summarize_rcsb_search(data: dict[str, Any]) -> dict[str, str]:
    total = data.get("total_count") or data.get("totalCount")
    enriched_hits = data.get("hits") if isinstance(data.get("hits"), list) else []
    raw_hits = data.get("result_set") or data.get("resultSet") or enriched_hits or []
    n = len(raw_hits) if isinstance(raw_hits, list) else 0
    resolution_by_id: dict[str, Any] = {}
    if isinstance(enriched_hits, list):
        for row in enriched_hits:
            if isinstance(row, dict):
                pid = str(row.get("pdb_id") or row.get("identifier") or "").upper()
                if pid and row.get("resolution") is not None:
                    resolution_by_id[pid] = row.get("resolution")
    ids: list[str] = []
    if isinstance(raw_hits, list):
        for row in raw_hits[:8]:
            if isinstance(row, dict):
                pid = str(row.get("identifier") or row.get("pdb_id") or row.get("entry_id") or "").upper()
                if pid:
                    ids.append(pid)
            elif isinstance(row, str):
                ids.append(row.upper())
    summary = f"匹配 {total if total is not None else n} 条"
    if ids:
        summary += f"，示例 {', '.join(ids[:5])}"
    lines = [summary]
    display_rows = enriched_hits if enriched_hits else raw_hits
    if isinstance(display_rows, list):
        for row in display_rows[:12]:
            if not isinstance(row, dict):
                continue
            pid = str(row.get("identifier") or row.get("pdb_id") or "").upper()
            score = row.get("score")
            resolution = row.get("resolution")
            if resolution is None and pid:
                resolution = resolution_by_id.get(pid)
            if not pid:
                continue
            parts = [pid]
            if resolution is not None:
                parts.append(f"{resolution} Å")
            elif isinstance(score, (int, float)):
                parts.append(f"相关性 {score:.2f}")
            lines.append(" · ".join(parts))
    return {"result": summary, "detail": "\n".join(lines)}


def _summarize_rcsb_entry(data: dict[str, Any]) -> dict[str, str]:
    entry = data.get("entry") if "entry" in data else data
    if not isinstance(entry, dict):
        entry = data
    info = entry.get("rcsb_entry_info") or entry
    acc = entry.get("rcsb_accession_info") or {}
    struct = entry.get("struct") or {}
    res = info.get("resolution_combined")
    method = info.get("experimental_method") or info.get("experimental_methods")
    if isinstance(method, list):
        method = method[0] if method else ""
    title = (struct.get("title") or entry.get("title") or "").strip()
    date = acc.get("initial_release_date") or acc.get("deposit_date") or ""
    bits = []
    if res is not None:
        bits.append(f"分辨率 {res} Å")
    if method:
        bits.append(str(method))
    if date:
        bits.append(f"发布 {str(date)[:10]}")
    summary = " · ".join(bits) if bits else "已获取元数据"
    detail_parts = [summary]
    if title:
        detail_parts.append(title[:200])
    return {"result": summary, "detail": "\n".join(detail_parts)}


def _summarize_truncated_ai4drug_json(text: str, tool_key: str = "") -> dict[str, str] | None:
    """当过程日志里的 JSON 被截断无法解析时，用关键字段做短摘要。"""
    raw = text or ""
    key = (tool_key or "").lower()
    if not key:
        if '"pockets"' in raw:
            key = "pocket_prediction"
        elif '"docking"' in raw or '"docking_results"' in raw:
            key = "molecular_docking"
        elif '"configs"' in raw:
            key = "docking_box_config"
        elif '"receptors"' in raw:
            key = "receptor_preparation"
        elif '"ligands"' in raw:
            key = "ligand_preparation"
        elif '"targets"' in raw:
            key = "protein_acquisition"
        elif "conformer" in raw:
            key = "conformer_generation"

    if "molecular_docking" in key:
        m = re.search(r'"score"\s*:\s*(-?[0-9.]+)', raw)
        mid = re.search(r'"molecule_id"\s*:\s*"([^"]+)"', raw)
        summary = "分子对接完成"
        if m:
            summary += f"，最佳 {float(m.group(1)):.3f} kcal/mol"
        detail = mid.group(1) if mid else summary
        return {"result": summary, "detail": detail}

    if "pocket_prediction" in key:
        pockets_raw = re.findall(
            r'\{[^{}]*"pocket_id"\s*:\s*"([^"]+)"[^{}]*"score"\s*:\s*(-?[0-9.]+)[^{}]*"probability"\s*:\s*(-?[0-9.]+)[^{}]*\}',
            raw,
        )
        if not pockets_raw:
            pockets_raw = re.findall(
                r'"pocket_id"\s*:\s*"([^"]+)"[^}]*?"score"\s*:\s*(-?[0-9.]+)[^}]*?"probability"\s*:\s*(-?[0-9.]+)',
                raw,
                re.S,
            )
        lines = []
        for pid, score, prob in pockets_raw[:8]:
            lines.append(f"{pid} · 评分 {score} · 概率 {prob}")
        summary = "口袋预测完成"
        if lines:
            summary = f"识别 {len(lines)} 个结合口袋，主口袋 {lines[0].split(' · ')[0]}"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "conformer_generation" in key:
        mid = re.search(r'"id"\s*:\s*"([^"]+)"', raw) or re.search(
            r'"molecule_id"\s*:\s*"([^"]+)"', raw
        )
        n = re.search(r'"num_conformers"\s*:\s*(\d+)', raw)
        summary = "3D构象生成完成"
        if n:
            summary = f"已生成构象（{n.group(1)} 个）"
        detail = mid.group(1) if mid else summary
        return {"result": summary, "detail": detail}

    if "docking_box_config" in key:
        pid = re.search(r'"pocket_id"\s*:\s*"([^"]+)"', raw)
        summary = f"已配置对接盒，{pid.group(1)}" if pid else "对接盒配置完成"
        return {"result": summary, "detail": summary}

    if "ligand_preparation" in key:
        mid = re.search(r'"molecule_id"\s*:\s*"([^"]+)"', raw)
        summary = "配体准备完成"
        return {"result": summary, "detail": mid.group(1) if mid else summary}

    if "receptor_preparation" in key:
        tid = re.search(r'"target_id"\s*:\s*"([^"]+)"', raw)
        summary = "受体准备完成"
        return {"result": summary, "detail": tid.group(1) if tid else summary}

    if "protein_acquisition" in key:
        gene = re.search(r'"gene_symbol"\s*:\s*"([^"]+)"', raw)
        pdb = re.search(r'"pdb_id"\s*:\s*"([^"]+)"', raw)
        bits = []
        if gene:
            bits.append(gene.group(1))
        if pdb:
            bits.append(f"PDB {pdb.group(1).upper()}")
        summary = " · ".join(bits) if bits else "蛋白质结构已获取"
        return {"result": summary, "detail": summary}

    return None


def _extract_structured_content(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if raw.startswith("structuredContent:"):
        raw = raw[len("structuredContent:") :].strip()
    data = _extract_json_blob(raw)
    if not isinstance(data, dict):
        return None
    if "success" in data:
        return data
    # conformer_generation 等直接返回 {tool, session_id, ...} 无 success 字段
    if data.get("tool") in _AI4DRUG_SHORT_NAMES:
        return {"success": True, "data": data, "message": ""}
    if any(
        k in data
        for k in (
            "targets",
            "pockets",
            "receptors",
            "ligands",
            "molecules",
            "configs",
            "docking_results",
            "docking_boxes",
        )
    ):
        return {"success": True, "data": data, "message": ""}
    inner = data.get("data")
    if isinstance(inner, dict) and any(
        k in inner
        for k in (
            "targets",
            "pockets",
            "receptors",
            "ligands",
            "molecules",
            "configs",
            "docking_results",
        )
    ):
        return {
            "success": data.get("success", True),
            "data": inner,
            "message": str(data.get("message") or ""),
        }
    return None


def _ai4drug_tool_label(tool_name: str) -> str:
    label = _AI4DRUG_TOOL_LABELS.get(tool_name or "")
    if label:
        return label
    name = (tool_name or "").strip().lower()
    if name.startswith("ai4drug__"):
        return name.replace("ai4drug__", "").replace("_", " ")
    short = _AI4DRUG_SHORT_NAMES.get(name)
    if short:
        return short
    return "AI4Drug"


def _clip_detail(text: str, *, max_chars: int = 280, max_lines: int = 6) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()][:max_lines]
    out = "\n".join(lines)
    if len(out) > max_chars:
        out = out[: max_chars - 1] + "…"
    return out


def _summarize_ai4drug_structured(tool_name: str, raw: str) -> dict[str, str] | None:
    payload = _extract_structured_content(raw)
    if not payload:
        # validation / plain error without success wrapper
        low = (raw or "").lower()
        if "validation error" in low or "unexpected keyword" in low:
            label = _ai4drug_tool_label(tool_name) if "ai4drug" in (tool_name or "") else "工具"
            tip = "参数格式不正确，请按工具 schema 传参后重试"
            if "conformer" in low:
                tip = "构象参数需放在 params 对象中（如 method/num_conformers），不要平铺为顶层参数"
            return {"result": f"{label}失败", "detail": tip}
        truncated = _summarize_truncated_ai4drug_json(raw, tool_name)
        if truncated:
            return truncated
        return None

    success = payload.get("success")
    message = str(payload.get("message") or "").strip()
    inner = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    tool_key = (tool_name or "").lower()
    if tool_key in ("exec", "bash", "shell", "tool", "") or "ai4drug" not in tool_key:
        inferred = _infer_ai4drug_tool_key(
            {"tool": inner.get("tool") or payload.get("tool"), **payload, "data": inner}
            if isinstance(inner, dict)
            else payload
        )
        # also try raw data shape
        if not inferred and isinstance(inner, dict):
            inferred = _infer_ai4drug_tool_key({"success": success, "data": inner, "tool": inner.get("tool")})
        if not inferred:
            inferred = _infer_ai4drug_tool_key(payload if isinstance(payload, dict) else {})
        if inferred:
            tool_key = inferred

    label = _ai4drug_tool_label(tool_key if tool_key.startswith("ai4drug") else f"ai4drug__{tool_key}")

    if not success:
        # 失败时也尽量从 message 推断工具名
        if tool_key in ("exec", "bash", "shell", "tool", "") or "ai4drug" not in tool_key:
            ml = message.lower()
            if "docking box" in ml or "box config" in ml:
                tool_key = "ai4drug__docking_box_config"
            elif "docking" in ml:
                tool_key = "ai4drug__molecular_docking"
            elif "pocket" in ml:
                tool_key = "ai4drug__pocket_prediction"
            elif "receptor" in ml:
                tool_key = "ai4drug__receptor_preparation"
            elif "ligand" in ml:
                tool_key = "ai4drug__ligand_preparation"
            elif "admet" in ml or "evaluation" in ml:
                tool_key = "ai4drug__molecule_evaluation"
            elif "retrosynt" in ml:
                tool_key = "ai4drug__retrosynthesis"
            label = _ai4drug_tool_label(
                tool_key if tool_key.startswith("ai4drug") else f"ai4drug__{tool_key}"
            )
        detail = message or "执行失败"
        low = detail.lower()
        if "no pockets" in low:
            detail = "会话中尚无口袋。请先执行口袋预测，再配置对接盒。"
        elif "no pockets resolved" in low:
            detail = "未找到有效口袋。请先执行口袋预测，并使用返回的完整 pocket_id（如 EGFR_1M14_pocket1），不要只传 pocket1。"
        elif "invalid molecule_id format" in low:
            detail = (
                "分子 ID 必须为 `{pocket_id}_mol0`（如 EGFR_3W2S_pocket1_mol0）。"
                "请先用 conformer_generation 以该 id 写入同一猛犸 session_id，"
                "再 ligand_preparation / molecular_docking；禁止用 gefitinib 等药物名作为 id。"
            )
        elif "missing molecules in session" in low:
            detail = (
                "会话中不存在该分子。请先用 conformer_generation（molecules[].id 为 `{pocket_id}_mol0`，"
                "必须传猛犸 session_id），再 ligand_preparation。"
            )
        elif "target" in low and ("not found" in low or "session" in low):
            detail = (
                "靶点未在当前 session 注册。请确认全程使用同一猛犸 session_id，"
                "且 conformer_generation 不要省略 session_id（否则会创建孤立会话）。"
            )
        return {"result": f"{label}失败", "detail": _clip_detail(detail)}

    if "molecule_design" in tool_key:
        molecules = inner.get("molecules") or []
        if not isinstance(molecules, list):
            molecules = []
        lines: list[str] = []
        ai_count = 0
        chembl_count = 0
        for mol in molecules:
            if isinstance(mol, dict) and (mol.get("source") == "chembl" or "chembl" in str(mol.get("molecule_id", "")).lower()):
                chembl_count += 1
            elif isinstance(mol, dict):
                ai_count += 1
        summary = f"已生成 {len(molecules)} 个候选分子"
        if ai_count or chembl_count:
            summary += f"（AI {ai_count} + ChEMBL {chembl_count}）"
        for i, mol in enumerate(molecules[:8], 1):
            if not isinstance(mol, dict):
                continue
            mid = str(mol.get("molecule_id") or f"mol{i}")
            smiles = str(mol.get("smiles") or "").strip()
            parts = [mid]
            if smiles:
                parts.append(smiles[:72] + ("…" if len(smiles) > 72 else ""))
            if mol.get("chembl_id"):
                parts.append(str(mol["chembl_id"]))
            if mol.get("pref_name"):
                parts.append(str(mol["pref_name"]))
            if mol.get("pchembl_value") is not None:
                parts.append(f"pChEMBL {mol['pchembl_value']}")
            lines.append(f"{i}. " + " · ".join(parts))
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "receptor_preparation" in tool_key:
        receptors = inner.get("receptors") or []
        if not isinstance(receptors, list):
            receptors = []
        lines = []
        for rec in receptors[:6]:
            if not isinstance(rec, dict):
                continue
            tid = str(rec.get("target_id") or "")
            bits = [tid] if tid else []
            if rec.get("receptor_path") or rec.get("pdbqt_path"):
                bits.append("受体 PDBQT 已生成")
            if bits:
                lines.append(" · ".join(bits))
        summary = f"已制备 {len(receptors)} 个受体" if receptors else "受体准备完成"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "pocket_prediction" in tool_key:
        pockets = inner.get("pockets") or []
        if not isinstance(pockets, list):
            pockets = []
        lines = []
        for pocket in pockets[:6]:
            if not isinstance(pocket, dict):
                continue
            pid = str(pocket.get("pocket_id") or "")
            bits = [pid] if pid else []
            score = pocket.get("score")
            prob = pocket.get("probability")
            if score is not None:
                bits.append(f"评分 {score}")
            if prob is not None:
                bits.append(f"概率 {prob:.2f}")
            if bits:
                lines.append(" · ".join(bits))
        summary = f"识别 {len(pockets)} 个结合口袋"
        if lines:
            summary += f"，主口袋 {lines[0].split(' · ')[0]}"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "docking_box_config" in tool_key:
        boxes = (
            inner.get("configs")
            or inner.get("docking_boxes")
            or inner.get("boxes")
            or []
        )
        if not isinstance(boxes, list):
            boxes = []
        lines = []
        for box in boxes[:6]:
            if not isinstance(box, dict):
                continue
            pid = str(box.get("pocket_id") or "")
            center = box.get("center") or box.get("center_coords")
            size = box.get("size") or box.get("box_size")
            bits = [pid] if pid else []
            if isinstance(center, (list, tuple)) and len(center) >= 3:
                bits.append(
                    f"中心 ({float(center[0]):.1f}, {float(center[1]):.1f}, {float(center[2]):.1f})"
                )
            elif isinstance(center, dict):
                bits.append(
                    "中心 "
                    f"({float(center.get('x', 0)):.1f}, {float(center.get('y', 0)):.1f}, "
                    f"{float(center.get('z', 0)):.1f})"
                )
            if isinstance(size, (list, tuple)) and len(size) >= 3:
                bits.append(
                    f"尺寸 {float(size[0]):.1f}×{float(size[1]):.1f}×{float(size[2]):.1f} Å"
                )
            elif isinstance(size, dict):
                bits.append(
                    f"尺寸 {float(size.get('x', 0)):.1f}×{float(size.get('y', 0)):.1f}×"
                    f"{float(size.get('z', 0)):.1f} Å"
                )
            if bits:
                lines.append(" · ".join(bits))
        summary = f"已配置 {len(boxes)} 个对接盒" if boxes else (message or "对接盒配置完成")
        if lines:
            summary += f"，{lines[0].split(' · ')[0]}"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "molecular_docking" in tool_key:
        molecules = inner.get("molecules") or inner.get("docking_results") or []
        if not isinstance(molecules, list):
            molecules = []
        lines = []
        best_score: float | None = None
        for mol in molecules[:8]:
            if not isinstance(mol, dict):
                continue
            mid = str(mol.get("molecule_id") or "")
            pocket = str(mol.get("pocket_id") or "")
            docking = mol.get("docking") if isinstance(mol.get("docking"), dict) else {}
            score = docking.get("score") if docking else mol.get("score")
            bits = [b for b in (mid, pocket) if b]
            if score is not None:
                bits.append(f"打分 {float(score):.3f} kcal/mol")
                if best_score is None or float(score) < best_score:
                    best_score = float(score)
            pose = docking.get("pose_path") or mol.get("pose_path")
            if pose:
                bits.append("姿势已生成")
            if bits:
                lines.append(" · ".join(bits))
        summary = "分子对接完成"
        if best_score is not None:
            summary += f"，最佳 {best_score:.3f} kcal/mol"
        # 一行摘要即可，勿把整分子列表当最终回答复读
        detail = lines[0] if lines else summary
        return {"result": summary, "detail": _clip_detail(detail, max_chars=160)}

    if "conformer_generation" in tool_key:
        molecules = inner.get("molecules") or []
        if not molecules and isinstance(inner.get("output"), dict):
            molecules = inner["output"].get("molecules") or inner["output"].get("results") or []
        if not molecules:
            molecules = inner.get("results") or []
        if not isinstance(molecules, list):
            molecules = []
        if not molecules and isinstance(inner.get("input"), dict):
            src = inner["input"].get("molecules") or []
            if isinstance(src, list):
                molecules = src
        lines = []
        for mol in molecules[:6]:
            if not isinstance(mol, dict):
                continue
            mid = str(mol.get("id") or mol.get("molecule_id") or "")
            nconf = mol.get("num_conformers") or mol.get("conformer_count")
            bits = [mid] if mid else []
            if nconf is not None:
                bits.append(f"{nconf} 个构象")
            smiles = str(mol.get("smiles") or "").strip()
            if smiles:
                bits.append(smiles[:48] + ("…" if len(smiles) > 48 else ""))
            if bits:
                lines.append(" · ".join(bits))
        count = len(molecules)
        summary = f"已生成 {count} 个分子构象" if count else "3D构象生成完成"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "ligand_preparation" in tool_key:
        ligands = inner.get("ligands") or []
        if not isinstance(ligands, list):
            ligands = []
        lines = []
        for lig in ligands[:8]:
            if not isinstance(lig, dict):
                continue
            mid = str(lig.get("molecule_id") or lig.get("id") or "")
            path = str(lig.get("pdbqt_path") or lig.get("output_path") or "")
            bits = [mid] if mid else []
            if path:
                bits.append("PDBQT 已生成")
            if bits:
                lines.append(" · ".join(bits))
        summary = f"已制备 {len(ligands)} 个配体"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "molecule_evaluation" in tool_key or ("admet" in tool_key and "docking" not in tool_key):
        molecules = inner.get("molecules") or inner.get("evaluations") or inner.get("results") or []
        if not isinstance(molecules, list):
            molecules = []
        lines = []
        for mol in molecules[:6]:
            if not isinstance(mol, dict):
                continue
            mid = str(mol.get("molecule_id") or mol.get("id") or "")
            admet = mol.get("admet") if isinstance(mol.get("admet"), dict) else None
            bits = [mid] if mid else []
            if isinstance(admet, dict):
                for key, label in (
                    ("QED", "QED"),
                    ("qed", "QED"),
                    ("BBB", "BBB"),
                    ("Bioavailability", "口服生物利用度"),
                    ("hERG", "hERG"),
                    ("DILI", "DILI"),
                    ("AMES", "AMES"),
                ):
                    if admet.get(key) is not None:
                        try:
                            bits.append(f"{label} {float(admet[key]):.2f}")
                        except (TypeError, ValueError):
                            bits.append(f"{label} {admet[key]}")
            if bits:
                lines.append(" · ".join(str(b) for b in bits))
        summary = f"已评估 {len(molecules)} 个分子 ADMET" if molecules else (message or "ADMET 评估完成")
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "retrosynthesis" in tool_key:
        routes = inner.get("routes") or inner.get("synthesis_routes") or inner.get("results") or []
        if not isinstance(routes, list):
            routes = []
        molecules = inner.get("molecules") or []
        n = len(routes) or len(molecules) if isinstance(molecules, list) else len(routes)
        summary = f"已生成 {n} 条合成路线" if n else (message or "逆合成分析完成")
        lines = []
        for i, route in enumerate(routes[:4], 1):
            if isinstance(route, dict):
                score = route.get("score") or route.get("confidence")
                steps_n = route.get("num_steps") or route.get("steps")
                bits = [f"路线{i}"]
                if score is not None:
                    bits.append(f"评分 {score}")
                if steps_n is not None and not isinstance(steps_n, list):
                    bits.append(f"{steps_n} 步")
                elif isinstance(steps_n, list):
                    bits.append(f"{len(steps_n)} 步")
                lines.append(" · ".join(bits))
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "target_discovery" in tool_key:
        targets = inner.get("targets") or []
        if not isinstance(targets, list):
            targets = []
        lines = []
        for target in targets[:6]:
            if not isinstance(target, dict):
                continue
            gene = str(target.get("gene_symbol") or "")
            score = target.get("association_score")
            pdbs = target.get("pdb_preview") or target.get("pdb_preview_ids") or []
            if isinstance(pdbs, list):
                pdb_text = ", ".join(str(p) for p in pdbs[:4])
            else:
                pdb_text = ""
            bits = [gene] if gene else []
            if score is not None:
                bits.append(f"关联分 {float(score):.3f}")
            if pdb_text:
                bits.append(f"PDB {pdb_text}")
            if bits:
                lines.append(" · ".join(bits))
        summary = f"发现 {len(targets)} 个靶点"
        if lines:
            summary += f"，Top {lines[0].split(' · ')[0]}"
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    if "protein_acquisition" in tool_key:
        targets = inner.get("targets") or []
        if not isinstance(targets, list):
            targets = []
        lines = []
        pdb_ids: list[str] = []
        for target in targets[:6]:
            if not isinstance(target, dict):
                continue
            gene = str(target.get("gene_symbol") or "")
            pdb = str(target.get("pdb_id") or "").upper()
            tid = str(target.get("target_id") or "")
            if pdb and _is_valid_pdb_id(pdb):
                pdb_ids.append(pdb)
            bits = []
            if gene:
                bits.append(gene)
            if pdb:
                bits.append(f"PDB {pdb}")
            if tid:
                bits.append(tid)
            protein = target.get("protein") if isinstance(target.get("protein"), dict) else {}
            if protein.get("clean_pdb_path"):
                bits.append("结构已清洗")
            if bits:
                lines.append(" · ".join(bits))
        summary = "蛋白质结构已获取"
        if pdb_ids:
            summary = f"{lines[0].split(' · ')[0] if lines else '蛋白'} · PDB " + ", ".join(dict.fromkeys(pdb_ids))
        return {"result": summary, "detail": _clip_detail("\n".join(lines) if lines else summary)}

    return None


def _summarize_ai4drug_protein(text: str) -> dict[str, str] | None:
    if _extract_structured_content(text):
        return None
    if "molecule_design" in text or '"molecules"' in text:
        return None
    if "protein_acquisition" not in text and "clean_pdb_path" not in text:
        return None
    pdb_ids: list[str] = []
    for m in re.finditer(r'"pdb_id"\s*:\s*"([A-Za-z0-9]{4})"', text):
        pid = m.group(1).upper()
        if _is_valid_pdb_id(pid):
            pdb_ids.append(pid)
    for m in re.finditer(r'"pdb_preview"\s*:\s*\[(.*?)\]', text, re.S):
        for token in re.findall(r'"([A-Za-z0-9]{4})"', m.group(1)):
            pid = token.upper()
            if _is_valid_pdb_id(pid):
                pdb_ids.append(pid)
    pdb_ids = list(dict.fromkeys(pdb_ids))[:6]
    m = re.search(r'"gene_symbol"\s*:\s*"([^"]+)"', text)
    gene = m.group(1) if m else ""
    bits = []
    if gene:
        bits.append(gene)
    if pdb_ids:
        bits.append("PDB " + ", ".join(pdb_ids))
    if "clean_pdb_path" in text:
        bits.append("结构已下载并清洗")
    if not bits:
        return None
    summary = " · ".join(bits)
    detail = summary
    if pdb_ids:
        detail += "\n" + "\n".join(f"PDB {p}" for p in pdb_ids)
    return {"result": summary, "detail": detail}


def friendly_tool_step(tool_name: str, arguments: Any) -> dict[str, str]:
    """返回 title / name / input / kind，用于过程面板展示。"""
    name = (tool_name or "tool").strip()
    args = arguments if isinstance(arguments, dict) else {}

    ai4drug = _friendly_ai4drug(name, args)
    if ai4drug:
        title, display_name, inp = ai4drug
        kind = "tool"
    elif web := _friendly_web_tool(name, args):
        title, display_name, inp, kind = web
    elif name in ("read", "Read", "read_file"):
        title, display_name, inp, kind = _friendly_read(args)
    elif name in ("exec", "bash", "shell", "Bash"):
        title, display_name, inp, kind = _friendly_exec(args)
    elif name.lower() in ("process", "process_tool"):
        action = str(args.get("action") or args.get("command") or "poll")
        title, display_name, inp, kind = ("后台进程", "后台进程", action[:80], "tool")
    else:
        title, display_name, inp, kind = _friendly_generic(name, arguments if arguments is not None else args)

    return {
        "title": title,
        "name": display_name,
        "input": inp,
        "kind": kind,
    }


def _summarize_mammoth_tool_payload(data: dict[str, Any]) -> dict[str, str] | None:
    if "pdb_id" in data and (
        "experimental_method" in data or "resolution" in data or "ligands" in data
    ):
        return _summarize_mammoth_pdb_metadata(data)
    if "total_count" in data or "result_set" in data or "resultSet" in data or "hits" in data:
        return _summarize_rcsb_search(data)
    if "rcsb_entry_info" in data or data.get("entry"):
        return _summarize_rcsb_entry(data)
    if "download_url" in data and ("reachable" in data or "mirror" in data):
        pid = str(data.get("query") or data.get("pdb_id") or "").upper()
        if pid:
            ok = "可下载" if data.get("reachable") else "暂不可达"
            url = str(data.get("download_url") or "")
            thumb = str(data.get("thumbnail_url") or "")
            detail_parts = [f"下载: {url}"] if url else []
            if thumb:
                detail_parts.append(f"预览图: {thumb}")
            detail_parts.append(f"3D 预览: https://www.rcsb.org/3d-view/{pid}")
            return {
                "result": f"PDB {pid} {ok}",
                "detail": "\n".join(detail_parts),
            }
    return None


def summarize_tool_result(tool_name: str, raw: str) -> dict[str, str]:
    """把工具原始输出压成「结果摘要 + 详情」，对齐 MatVenus 的 输出 区。"""
    text = (raw or "").strip()
    if not text:
        return {"result": "（无输出）", "detail": ""}

    data = _extract_json_blob(text)
    if isinstance(data, dict):
        mammoth_summary = _summarize_mammoth_tool_payload(_unwrap_tool_result_payload(data))
        if mammoth_summary:
            return mammoth_summary
        if data.get("error") and data.get("database_id"):
            err = str(data.get("error") or data.get("message") or "接口错误")
            return {"result": "接口调用失败", "detail": err[:300]}

    ai4drug_structured = _summarize_ai4drug_structured(tool_name, text)
    if ai4drug_structured:
        return ai4drug_structured

    ai4drug_summary = _summarize_ai4drug_protein(text)
    if ai4drug_summary:
        return ai4drug_summary

    if _is_exec_tool(tool_name):
        exec_summary = _summarize_exec_output(text)
        if exec_summary:
            return exec_summary

    if _is_web_tool(tool_name):
        web_summary = _summarize_web_search(text, tool_name)
        if web_summary:
            return web_summary

    if isinstance(data, dict):
        mammoth_summary = _summarize_mammoth_tool_payload(data)
        if mammoth_summary:
            return mammoth_summary
        if any(k in data for k in ("rcsb_entry_info", "struct", "audit_author", "reflns")):
            return _summarize_rcsb_entry(data)

    exec_summary = _summarize_exec_output(text)
    if exec_summary:
        return exec_summary

    if text.startswith("{") and ("property_list" in text or "molecular_weight" in text):
        try:
            props_data = json.loads(text)
            props = props_data.get("property_list") or []
            bits = []
            for p in props[:6]:
                label = p.get("label") or p.get("key") or ""
                val = p.get("value")
                unit = p.get("unit") or ""
                if label and val is not None:
                    bits.append(f"{label} {val}{' ' + unit if unit else ''}".strip())
            if bits:
                return {
                    "result": "；".join(bits[:3]),
                    "detail": "\n".join(bits),
                }
        except json.JSONDecodeError:
            pass
        mw = re.search(r'"molecular_weight"\s*:\s*([0-9.]+)', text)
        if mw:
            return {"result": f"分子量 {mw.group(1)} g/mol", "detail": text[:500]}

    if text.startswith("---") and "name:" in text[:80]:
        m = re.search(r"^name:\s*([^\n]+)", text, re.M)
        d = re.search(r'^description:\s*"?([^"\n]+)"?', text, re.M)
        skill_name = (m.group(1).strip() if m else tool_name) or "skill"
        label = _skill_display_name(skill_name)
        desc = (d.group(1).strip() if d else "")[:120]
        return {
            "result": f"已加载技能「{label}」",
            "detail": desc or text[:300],
        }

    if "reachable" in text and "download_url" in text:
        try:
            dl = json.loads(text) if text.startswith("{") else None
            if isinstance(dl, dict) and dl.get("query"):
                pid = str(dl["query"]).upper()
                ok = "可下载" if dl.get("reachable") else "暂不可达"
                return {
                    "result": f"PDB {pid} {ok}",
                    "detail": f"镜像 {dl.get('mirror', 'rcsb')}\n{dl.get('download_url', '')}",
                }
        except json.JSONDecodeError:
            pass

    cleaned = strip_paths(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # 避免把整段 JSON / structuredContent 再铺一遍
    if cleaned.startswith("{") or cleaned.startswith("structuredContent"):
        ai4 = _summarize_ai4drug_structured(tool_name, text)
        if ai4:
            return ai4
        return {"result": "工具执行完成", "detail": ""}
    # 读取 AI4Drug 报告 markdown：只保留标题一行
    if "逆合成分析报告" in text or "retrosynthesis" in text.lower() and text.lstrip().startswith("#"):
        return {"result": "已读取逆合成分析报告", "detail": ""}
    if "分子设计" in text and text.lstrip().startswith("#"):
        return {"result": "已读取分子设计报告", "detail": ""}
    if "ADMET" in text and text.lstrip().startswith("#"):
        return {"result": "已读取 ADMET 报告", "detail": ""}
    if "Process still running" in text or "(no new output)" in text:
        return {"result": "后台任务仍在运行", "detail": ""}
    if "Command still running" in text:
        return {"result": "命令仍在后台运行", "detail": "请等待工具返回完整结果，勿提前结束"}
    # process 输出的截断 JSON 片段（逆合成常见）
    if "policy_probability" in text or '"in_stock"' in text or "retrosynt" in text.lower():
        return {"result": "逆合成路线已生成", "detail": _clip_detail(strip_paths(text), max_chars=160)}
    if '"molecules"' in text and ("smiles" in text.lower() or "SMILES" in text):
        return {"result": "分子结果已返回", "detail": ""}
    summary = cleaned[:120] + ("…" if len(cleaned) > 120 else "")
    return {"result": summary or "执行完成", "detail": _clip_detail(cleaned, max_chars=280)}


def polish_ai4drug_exec_step(step: dict[str, Any]) -> dict[str, Any]:
    """把 mcporter/exec 步骤改写成友好 MCP 名称，并压缩 JSON 结果。"""
    out = dict(step)
    title = str(out.get("title") or "")
    name = str(out.get("name") or "")
    inp = str(out.get("input") or "")
    result = str(out.get("result") or "")
    detail = str(out.get("detail") or "")

    mcp = _parse_mcporter_ai4drug(inp)
    if mcp:
        t, n, i = mcp
        out["title"] = t
        out["name"] = n
        if i and i != "执行中":
            out["input"] = i
        title, name = t, n
    else:
        hx = _parse_huaxue_ai_curl(inp) or _parse_huaxue_ai_curl(title)
        if hx:
            t, n, i = hx
            out["title"] = t
            out["name"] = n
            if i and (not inp or inp.startswith("curl") or "3010" in inp):
                out["input"] = i
            title, name = t, n

    blob = result if len(result) >= len(detail) else detail
    blob = (blob or result or detail).strip()
    # 运行中的后台提示也要中文化，避免面板长时间显示英文 Command still running
    if str(out.get("status") or "").lower() == "running" and (
        "Command still running" in blob or "Process still running" in blob
    ):
        out["result"] = "命令仍在后台运行"
        out["detail"] = "请等待工具返回完整结果"
        blob = out["result"]
    needs_summary = (
        blob.startswith("{")
        or blob.lstrip().startswith("#")
        or "structuredContent" in blob
        or '"success"' in blob
        or '"targets"' in blob
        or '"pockets"' in blob
        or '"molecules"' in blob
        or '"receptors"' in blob
        or '"ligands"' in blob
        or '"configs"' in blob
        or "validation error" in blob.lower()
        or "unexpected keyword" in blob.lower()
        or "Command still running" in blob
        or "Process still running" in blob
        or "(no new output)" in blob
    )
    if needs_summary and str(out.get("status") or "done") in ("done", "failed", ""):
        short = None
        for k, v in _AI4DRUG_SHORT_NAMES.items():
            if v == name or v == title:
                short = k
                break
        tool_name = f"ai4drug__{short}" if short else "exec"
        summarized = summarize_tool_result(tool_name, blob if blob else result)
        if (not summarized or summarized.get("result") in ("工具执行完成", "执行完成")) and (
            "…" in blob or "..." in blob
        ):
            truncated = _summarize_truncated_ai4drug_json(blob, tool_name)
            if truncated:
                summarized = truncated
        if summarized and summarized.get("result") not in ("工具执行完成", "执行完成"):
            out["result"] = summarized.get("result") or out.get("result") or ""
            out["detail"] = summarized.get("detail") or ""
        elif summarized:
            # 兜底：至少去掉 JSON 大段
            out["result"] = summarized.get("result") or "执行完成"
            out["detail"] = summarized.get("detail") or ""
        if out.get("name") in ("exec", "执行命令"):
            data = _extract_json_blob(blob) or {}
            inferred = _infer_ai4drug_tool_key(data if isinstance(data, dict) else {})
            if not inferred:
                # 截断 JSON 时从标题/名称或字段嗅探
                for k, v in _AI4DRUG_SHORT_NAMES.items():
                    if v == out.get("name") or v == out.get("title"):
                        inferred = f"ai4drug__{k}"
                        break
            if inferred:
                label = _ai4drug_tool_label(inferred)
                out["title"] = label
                out["name"] = label
    return out


def _step_blob(step: dict[str, Any]) -> str:
    return f"{step.get('result', '')} {step.get('detail', '')} {step.get('input', '')}"


def _is_timeout_or_error_blob(blob: str) -> bool:
    low = (blob or "").lower()
    return any(
        token in low
        for token in (
            "timed out",
            "appears offline",
            "执行超时",
            "执行失败",
            "mcp 服务离线",
            "iserror",
            "validation error",
        )
    )


def seal_tool_attempt_lifecycle(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """保留失败尝试：超时/重试时把旧步骤标为 failed，而不是一直 running 或被成功覆盖。"""
    out = [dict(s) for s in steps]

    for i, step in enumerate(out):
        blob = _step_blob(step)
        if _is_timeout_or_error_blob(blob):
            step["status"] = "failed"
            if not str(step.get("result") or "").strip():
                step["result"] = "执行超时或失败"
        elif str(step.get("status") or "").lower() == "failed":
            if not str(step.get("result") or "").strip():
                step["result"] = "执行失败"

    # 子步骤（exec/后台进程）失败 → 向前收口仍 running 的 MCP 工具步骤
    for i, step in enumerate(out):
        if str(step.get("status") or "").lower() != "failed":
            continue
        if str(step.get("name") or "") not in ("后台进程", "process", "执行命令", "exec", "命令工具"):
            continue
        blob = _step_blob(step)
        if not _is_timeout_or_error_blob(blob):
            continue
        err = str(step.get("result") or "执行超时或失败")[:160]
        for j in range(i - 1, -1, -1):
            prev = out[j]
            if str(prev.get("status") or "").lower() != "running":
                continue
            if str(prev.get("kind") or "") != "tool":
                continue
            prev["status"] = "failed"
            if not str(prev.get("result") or "").strip() or "仍在" in str(prev.get("result") or ""):
                prev["result"] = err
            break

    # 同名工具重试：后出现的 running/done 尝试 → 前面的 running 标 failed
    for i, step in enumerate(out):
        if str(step.get("status") or "").lower() != "running":
            continue
        name = str(step.get("name") or "")
        if not name or name in ("后台进程", "process", "深度思考"):
            continue
        for later in out[i + 1 :]:
            if str(later.get("name") or "") != name:
                continue
            if str(later.get("kind") or "") != str(step.get("kind") or ""):
                continue
            if str(later.get("status") or "").lower() in ("running", "done"):
                step["status"] = "failed"
                if not str(step.get("result") or "").strip() or "仍在" in str(step.get("result") or ""):
                    step["result"] = "执行超时或失败，已重试"
                break

    return out


def polish_ai4drug_exec_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    polished = [polish_ai4drug_exec_step(s) for s in steps]
    # 后台 process / 截断 JSON 片段 → 友好摘要
    for step in polished:
        result = str(step.get("result") or "")
        detail = str(step.get("detail") or "")
        blob = result if len(result) >= len(detail) else detail
        if not blob:
            continue
        name = str(step.get("name") or "")
        if "policy_probability" in blob or '"in_stock"' in blob:
            step["title"] = "逆合成分析"
            step["name"] = "逆合成分析"
            step["result"] = "逆合成路线已生成"
            step["detail"] = ""
            if str(step.get("status")) == "running":
                step["status"] = "done"
            continue
        if name in ("后台进程", "process") and (
            blob.lstrip().startswith("{") or '"molecules"' in blob or '"routes"' in blob
        ):
            summarized = summarize_tool_result("exec", blob)
            if summarized and summarized.get("result") not in ("工具执行完成", "执行完成", ""):
                data = _extract_json_blob(blob) or {}
                inferred = _infer_ai4drug_tool_key(data if isinstance(data, dict) else {})
                if inferred:
                    label = _ai4drug_tool_label(inferred)
                    step["title"] = label
                    step["name"] = label
                step["result"] = summarized["result"]
                step["detail"] = summarized.get("detail") or ""
                if str(step.get("status")) == "running":
                    step["status"] = "done"

    # 仅清理：同名工具 poll 成功后，收口仍显示「仍在后台」的 exec（不覆盖已 failed 的重试记录）
    success_by_name: dict[str, dict[str, Any]] = {}
    for s in polished:
        key = str(s.get("name") or "")
        res = str(s.get("result") or "")
        if (
            key
            and str(s.get("status")) == "done"
            and res
            and "失败" not in res
            and "超时" not in res
            and "仍在" not in res
            and key not in ("后台进程", "process", "深度思考")
        ):
            success_by_name[key] = s
    for s in polished:
        key = str(s.get("name") or "")
        if str(s.get("status")) == "running" and key in success_by_name:
            if "仍在" in str(s.get("result") or ""):
                src = success_by_name[key]
                s["status"] = "done"
                s["result"] = src.get("result") or s.get("result")
                s["detail"] = src.get("detail") or ""
        elif str(s.get("status")) == "running" and "仍在" in str(s.get("result") or ""):
            # 若已有逆合成成功摘要，收口
            if any(
                str(x.get("name")) == "逆合成分析"
                and "路线已生成" in str(x.get("result") or "")
                for x in polished
            ):
                s["status"] = "done"
                s["title"] = "逆合成分析"
                s["name"] = "逆合成分析"
                s["result"] = "逆合成路线已生成"
                s["detail"] = ""

    # chemical_reaction：process poll 完成后，收口残留「命令仍在后台运行」的 curl
    poll_done = any(
        str(s.get("status")) == "done"
        and (
            str(s.get("name") or "") in ("后台进程", "process")
            or "poll" in str(s.get("input") or "").lower()
        )
        for s in polished
    )
    if poll_done:
        for s in polished:
            res = str(s.get("result") or "")
            if str(s.get("status")) == "running" and ("仍在" in res or "still running" in res.lower()):
                s["status"] = "done"
                if str(s.get("name") or "") in ("exec", "执行命令", "命令工具"):
                    # 尽量保留已解析的友好名
                    pass
                s["result"] = "工具执行完成"
                s["detail"] = ""

    polished = seal_tool_attempt_lifecycle(polished)
    return polished
