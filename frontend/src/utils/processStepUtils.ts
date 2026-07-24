import type { LiveProcessStep } from '../api/client'

const PDB_ID_RE = /\b([1-9][A-Z0-9]{3})\b/gi

export function isValidPdbId(id: string): boolean {
  const token = id.trim().toUpperCase()
  return token.length === 4 && /[A-Z]/.test(token)
}

export const WEB_TOOL_LABELS: Record<string, string> = {
  web_search: '网络搜索',
  websearch: '网络搜索',
  web_fetch: '网页抓取',
  webfetch: '网页抓取',
  brave_web_search: 'Brave 搜索',
  brave_search: 'Brave 搜索',
  tavily_search: 'Tavily 搜索',
  tavily: 'Tavily 搜索',
  exa_search: 'Exa 搜索',
  exa: 'Exa 搜索',
  desearch_web_search: 'Desearch 搜索',
  desearch: 'Desearch 搜索',
  parallel_web: 'Parallel 搜索',
  parallel_web_search: 'Parallel 搜索',
}

const WEB_DISPLAY_NAMES = new Set(Object.values(WEB_TOOL_LABELS))

export function stripProcessPaths(text: string): string {
  return text
    .replace(/(?:~|\/home\/|\/data\d?\/|\/tmp\/|\.\/)[^\s"']+/g, (p) => {
      const skill = p.match(/(?:skills|skill)[/\\]([^/\\]+)[/\\]SKILL\.md/i)
      if (skill) return `技能「${skill[1]}」`
      const base = p.replace(/\/+$/, '').split('/').pop()
      return base || '文件'
    })
    .trim()
}

const RUNTIME_NOISE_PATTERNS = [
  /command\s+still\s+running/i,
  /process\s+still\s+running/i,
  /\(no\s+new\s+output\)/i,
  /use\s+process\s*\(\s*list\/poll/i,
  /session\s+kind-/i,
  /命令仍在运行/,
  /进程仍在运行/,
  /需要轮询/,
  /让我再等/,
  /再轮询/,
  /<tool_call/i,
]

export function isExecOutputNoise(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  const low = t.toLowerCase()
  if (low.includes('autodock vina') && (low.includes('center_x') || low.includes('size_x'))) return true
  if (low.includes('center_x') && low.includes('size_x') && (low.includes('center_y') || low.includes('exhaustiveness'))) {
    return true
  }
  if (low.includes('data_pre_processing.py')) return true
  return false
}

export function isProcessDisplayNoise(text: string): boolean {
  return isProcessRuntimeNoise(text) || isExecOutputNoise(text)
}

const AUX_TOOL_NAMES = new Set([
  'exec',
  '执行命令',
  '命令工具',
  '读取报告',
  '后台进程',
  'process',
  '等待后台任务',
  'sessions_history',
  'session_history',
])

export function isAuxiliaryToolStep(step: Pick<LiveProcessStep, 'name' | 'title'>): boolean {
  const name = (step.name || '').trim()
  const title = (step.title || '').trim()
  return AUX_TOOL_NAMES.has(name) || AUX_TOOL_NAMES.has(title)
}

export function isProcessRuntimeNoise(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if (
    [
      '命令仍在后台运行',
      '请等待工具返回完整结果',
      '后台任务仍在运行',
      '命令仍在运行，需要轮询以确认完成。',
      '进程仍在运行，让我再等一会儿。',
      '进程仍在运行。让我再轮询一次。',
    ].includes(t)
  ) {
    return true
  }
  return RUNTIME_NOISE_PATTERNS.some((re) => re.test(t))
}

export function stripProcessRuntimeNoise(text: string): string {
  const raw = (text || '').trim()
  if (!raw) return ''
  if (isProcessDisplayNoise(raw)) return ''
  return raw
    .split('\n')
    .map((ln) => ln.trim())
    .filter((ln) => ln && !isProcessDisplayNoise(ln))
    .join('\n')
    .trim()
}

/** 工具原始 JSON / structuredContent 不应直接展示在前台（与后端 _looks_like_json_leak 对齐）。 */
export function isJsonLikeToolOutput(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if ((/^\d+\.\s+\S/m).test(t)) return false
  if (/^[\s{[]/.test(t)) return true
  if (/structuredContent/i.test(t)) return true
  if (/chembl_|opentargets/i.test(t) && t.length > 40) return true
  if (t.includes('"success"') && (t.includes('{') || t.length > 80)) return true
  if (/"tool"\s*:/.test(t) && (t.includes('"molecules"') || t.includes('"ligands"'))) return true
  if (/^[^"\n]*"\w+"\s*:/.test(t) && t.length > 36) return true
  return false
}

export function formatToolOutputForDisplay(text: string, fallback = ''): string {
  if (!text || isJsonLikeToolOutput(text)) return fallback
  return text
}

export function thinkingFullText(
  step: Pick<LiveProcessStep, 'detail' | 'result' | 'input' | 'title'>,
): string {
  return stripProcessPaths(step.detail || step.result || step.input || step.title || '')
}

/** 思考步骤折叠行：保留换行，仅压缩行内空白。 */
export function thinkingSummaryLine(text: string, maxLen = 96): string {
  const normalized = text.replace(/\r\n/g, '\n').trim()
  if (!normalized) return '整理思路中…'
  if (isProcessRuntimeNoise(normalized)) return '整理思路中…'
  const firstParagraph = normalized.split(/\n\s*\n/)[0]?.trim() || normalized
  const lines = firstParagraph
    .split('\n')
    .map((line) => line.replace(/[ \t]+/g, ' ').trim())
    .filter(Boolean)
  const preview = (lines.length > 0 ? lines.slice(0, 4).join('\n') : firstParagraph).trim()
  if (preview.length <= maxLen) return preview
  return `${preview.slice(0, maxLen - 1)}…`
}

function normalizeToolKey(name: string): string {
  return (name || '').trim().toLowerCase().replace(/-/g, '_')
}

export function formatWebToolLabel(name: string, title?: string): string | null {
  const candidates = [name, title].filter(Boolean) as string[]
  for (const raw of candidates) {
    const key = normalizeToolKey(raw)
    if (WEB_TOOL_LABELS[key]) return WEB_TOOL_LABELS[key]
    for (const [pattern, label] of Object.entries(WEB_TOOL_LABELS)) {
      if (key.includes(pattern) || raw.includes(label)) return label
    }
    if (WEB_DISPLAY_NAMES.has(raw) || WEB_DISPLAY_NAMES.has(raw.replace(/工具$/, ''))) {
      return raw.replace(/工具$/, '')
    }
  }
  return null
}

export function isWebToolStep(step: Pick<LiveProcessStep, 'kind' | 'name' | 'title'>): boolean {
  if (step.kind === 'web') return true
  return formatWebToolLabel(step.name, step.title) !== null
}

export function formatActionToolLabel(name: string, title?: string): string {
  const web = formatWebToolLabel(name, title)
  if (web) return web
  const raw = normalizeAi4DrugToolLabel((name || title || '').trim())
  return raw.replace(/工具$/, '') || '工具'
}

/** MatVenus-style label for process rows: 网络搜索 -> 网络搜索工具 */
export function formatExecutedToolLabel(step: Pick<LiveProcessStep, 'kind' | 'name' | 'title'>): string {
  if (step.kind === 'skill') {
    const base = (step.name || step.title || '技能').trim().replace(/技能$/, '')
    return `${base}技能`
  }
  const web = formatWebToolLabel(step.name, step.title)
  if (web) return `${web}工具`
  const raw = (step.name || step.title || '').trim()
  const base = raw.replace(/(工具|技能)$/, '') || '工具'
  // MCP / AI4Drug 步骤统一加「工具」后缀
  const blob = `${step.name} ${step.title}`.toLowerCase()
  if (
    blob.includes('ai4drug') ||
    ['蛋白质获取', '口袋预测', '分子对接', '受体准备', '配体准备', '对接盒配置', '3D构象生成', '靶点发现', '分子设计', 'ADMET', '逆合成', '流程汇总'].some(
      (k) => raw.includes(k),
    )
  ) {
    return `${base}工具`
  }
  if (raw === 'exec' || raw === '执行命令') return '命令工具'
  return base.endsWith('工具') ? base : `${base}工具`
}

export function formatStepStatusLine(
  step: Pick<LiveProcessStep, 'kind' | 'name' | 'title' | 'status'>,
  options?: { replyReady?: boolean },
): string {
  const label = formatExecutedToolLabel(step)
  const running = step.status === 'running' && !options?.replyReady
  if (running) return `正在执行${label}`
  if (step.status === 'failed') return `${label}执行失败`
  return `${label}执行完成`
}

const MCP_TOOL_NAME_HINTS = [
  'ai4drug',
  'mcporter',
  '蛋白质获取',
  '口袋预测',
  '分子对接',
  '受体准备',
  '配体准备',
  '对接盒配置',
  '3d构象生成',
  '靶点发现',
  '分子设计',
  'admet',
  '逆合成',
  '流程汇总',
] as const

const AI4DRUG_TOOL_LABELS: Record<string, string> = {
  target_discovery: '靶点发现',
  protein_acquisition: '蛋白质获取',
  pocket_prediction: '口袋预测',
  molecule_design: '分子设计',
  conformer_generation: '3D构象生成',
  receptor_preparation: '受体准备',
  ligand_preparation: '配体准备',
  docking_box_config: '对接盒配置',
  molecular_docking: '分子对接',
  molecule_evaluation: 'ADMET评估',
  retrosynthesis: '逆合成分析',
  pipeline_summary: '流程汇总',
}

export function normalizeAi4DrugToolLabel(name: string): string {
  const raw = (name || '').trim()
  if (!raw) return raw
  const key = raw.toLowerCase().replace(/^ai4drug__/, '').replace(/-/g, '_')
  return AI4DRUG_TOOL_LABELS[key] || raw
}

export function isMcpToolStep(
  step: Pick<LiveProcessStep, 'kind' | 'name' | 'title'> & { input?: string },
): boolean {
  if (step.kind === 'skill' || step.kind === 'thinking' || isWebToolStep(step)) return false
  const raw = `${step.name} ${step.title} ${step.input || ''}`.toLowerCase()
  if (raw.includes('ai4drug__') || raw.includes('ai4drug') || raw.includes('mcporter')) {
    return true
  }
  return MCP_TOOL_NAME_HINTS.some((hint) => raw.includes(hint))
}

export function isActionStep(
  stepOrKind:
    | LiveProcessStep['kind']
    | (Pick<LiveProcessStep, 'kind' | 'billable' | 'name' | 'title'> & { input?: string }),
): boolean {
  if (typeof stepOrKind === 'string') {
    return stepOrKind === 'tool' || stepOrKind === 'skill' || stepOrKind === 'web'
  }
  if (stepOrKind.billable === false) return false
  if (stepOrKind.name === '等待后台任务') return false
  if (stepOrKind.kind === 'tool' || stepOrKind.kind === 'skill' || stepOrKind.kind === 'web') {
    return true
  }
  return isMcpToolStep(stepOrKind)
}

export function stepBadgeLabel(
  kind: LiveProcessStep['kind'],
  name?: string,
  title?: string,
): string {
  if (kind === 'skill') return '技能'
  if (kind === 'thinking') return '思考'
  if (kind === 'web' || isWebToolStep({ kind, name: name || '', title: title || '' })) return '工具'
  if (isMcpToolStep({ kind, name: name || '', title: title || '' })) return 'MCP'
  return '工具'
}

export function stepBadgeClass(
  kind: LiveProcessStep['kind'],
  name?: string,
  title?: string,
): string {
  if (kind === 'skill') return 'bg-amber-100 text-amber-800'
  if (kind === 'thinking') return 'bg-violet-100 text-violet-700'
  if (kind === 'web' || isWebToolStep({ kind, name: name || '', title: title || '' })) {
    return 'bg-emerald-100 text-emerald-800'
  }
  if (isMcpToolStep({ kind, name: name || '', title: title || '' })) {
    return 'bg-blue-100 text-blue-700'
  }
  return 'bg-blue-100 text-blue-700'
}

export function extractPdbIds(...parts: Array<string | undefined>): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const part of parts) {
    if (!part) continue
    for (const m of part.matchAll(PDB_ID_RE)) {
      const id = m[1].toUpperCase()
      if (!isValidPdbId(id) || seen.has(id)) continue
      seen.add(id)
      out.push(id)
    }
  }
  return out
}

export function pdbThumbnailUrl(pdbId: string): string {
  return `https://cdn.rcsb.org/images/structures/${pdbId.toLowerCase()}_assembly-1.jpeg`
}

export function pdbDownloadUrl(pdbId: string): string {
  return `https://files.rcsb.org/download/${pdbId.toUpperCase()}.pdb`
}

export function pdbRcsbPageUrl(pdbId: string): string {
  return `https://www.rcsb.org/structure/${pdbId.toUpperCase()}`
}

export function pdb3dViewUrl(pdbId: string): string {
  return `https://www.rcsb.org/3d-view/${pdbId.toUpperCase()}`
}

export function isPdbRelatedStep(step: LiveProcessStep): boolean {
  const blob = `${step.title} ${step.name} ${step.input} ${step.result}`.toLowerCase()
  return (
    blob.includes('pdb') ||
    step.name.includes('蛋白质获取') ||
    step.title.includes('PDB')
  )
}
