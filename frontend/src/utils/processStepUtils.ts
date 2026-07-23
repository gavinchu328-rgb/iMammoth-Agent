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
  const raw = (name || title || '').trim()
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

export function isActionStep(kind: LiveProcessStep['kind']): boolean {
  return kind === 'tool' || kind === 'skill' || kind === 'web'
}

export function isMcpToolStep(step: Pick<LiveProcessStep, 'kind' | 'name' | 'title'>): boolean {
  if (step.kind === 'skill' || isWebToolStep(step)) return false
  const raw = `${step.name} ${step.title}`.toLowerCase()
  return raw.includes('ai4drug__') || raw.includes('ai4drug')
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
