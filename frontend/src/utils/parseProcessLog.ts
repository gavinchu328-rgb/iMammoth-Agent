import {
  isAuxiliaryToolStep,
  isJsonLikeToolOutput,
  isProcessDisplayNoise,
  isValidPdbId,
  normalizeAi4DrugToolLabel,
  stripProcessRuntimeNoise,
} from './processStepUtils'
import {
  extractTrailingModelFinal,
  isFinalAnswerUnusable,
  sanitizeFinalAnswerText,
} from './contentFilters'

export type ProcessStep = {
  index: number
  title: string
  type: '思考' | '工具' | '技能' | '搜索' | '未知'
  status: string
  name: string
  inputSummary: string
  resultSummary: string
  detail: string
  displayBlock?: string
}

export type ParsedAssistantReply = {
  hasProcess: boolean
  toolCount: number
  steps: ProcessStep[]
  finalAnswer: string
  raw: string
}

export { isLowQualityFinalAnswer } from './contentFilters'

function parseAdmetMetricLine(line: string): { molId: string; metrics: Record<string, string> } | null {
  const trimmed = line.trim()
  if (!trimmed) return null
  const parts = trimmed.replace(/\|/g, '·').split('·').map((p) => p.trim()).filter(Boolean)
  if (parts.length < 2) return null
  const molId = parts[0]
  const metrics: Record<string, string> = {}
  for (const part of parts.slice(1)) {
    const space = part.indexOf(' ')
    if (space > 0) {
      metrics[part.slice(0, space).trim()] = part.slice(space + 1).trim()
    } else {
      metrics[part] = '—'
    }
  }
  return { molId, metrics }
}

function formatAdmetFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  const title = (step.title || step.name || '').trim()
  const blob = `${title} ${step.name || ''}`.toLowerCase()
  if (!blob.includes('admet') && !blob.includes('molecule_evaluation') && !title.includes('评估')) {
    return null
  }
  const detail = (step.detail || step.resultSummary || '').trim()
  if (!detail || isJsonLikeToolOutput(detail)) return null
  const rows: { molId: string; metrics: Record<string, string> }[] = []
  for (const line of detail.split('\n')) {
    const parsed = parseAdmetMetricLine(line)
    if (parsed) rows.push(parsed)
  }
  if (rows.length === 0) {
    const parsed = parseAdmetMetricLine(detail.replace(/\n/g, ' · '))
    if (parsed) rows.push(parsed)
  }
  if (rows.length === 0) return null
  const metricOrder: string[] = []
  const seen = new Set<string>()
  for (const row of rows) {
    for (const key of Object.keys(row.metrics)) {
      if (!seen.has(key)) {
        seen.add(key)
        metricOrder.push(key)
      }
    }
  }
  const header = `| 分子 ID | ${metricOrder.join(' | ')} |`
  const sep = `| --- | ${metricOrder.map(() => '---').join(' | ')} |`
  const body = rows
    .map((row) => {
      const cells = metricOrder.map((k) => row.metrics[k] || '—')
      return `| ${row.molId} | ${cells.join(' | ')} |`
    })
    .join('\n')
  return `**${title || 'ADMET 评估结果'}**\n\n${header}\n${sep}\n${body}`
}

function formatPocketFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  const title = (step.title || step.name || '').trim()
  const blob = `${title} ${step.name || ''}`.toLowerCase()
  if (!blob.includes('口袋') && !blob.includes('pocket')) return null
  const detail = (step.detail || step.resultSummary || '').trim()
  if (!detail || isJsonLikeToolOutput(detail)) return null
  const rows: { pocketId: string; score: string; prob: string }[] = []
  for (const line of detail.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || !trimmed.includes('_pocket')) continue
    if (trimmed.includes('"pocket_id":') || trimmed.startsWith('{') || trimmed.startsWith('"')) continue
    const parts = trimmed.split('·').map((p) => p.trim())
    const pocketId = parts[0] || trimmed
    let score = ''
    let prob = ''
    for (const part of parts.slice(1)) {
      if (part.includes('评分')) score = part.replace('评分', '').trim()
      if (part.includes('概率')) prob = part.replace('概率', '').trim()
    }
    rows.push({ pocketId, score, prob })
  }
  if (rows.length === 0) return null
  const header = '| 口袋 ID | 评分 | 概率 |'
  const sep = '| --- | --- | --- |'
  const body = rows
    .map((row) => `| ${row.pocketId} | ${row.score || '—'} | ${row.prob || '—'} |`)
    .join('\n')
  return `**${title || '口袋预测结果'}**\n\n${header}\n${sep}\n${body}`
}

function formatMoleculeDesignFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  const title = (step.title || step.name || '').trim()
  const blob = `${title} ${step.name || ''}`.toLowerCase()
  if (!blob.includes('分子设计') && !blob.includes('molecule_design')) return null
  const result = (step.resultSummary || '').trim()
  const detail = (step.detail || '').trim()
  const body = detail || result
  if (!body || isJsonLikeToolOutput(body)) return null
  if (body === result && !body.includes('\n') && !body.includes('·') && !/^\d+\.\s/m.test(body)) {
    return null
  }
  const lines: string[] = []
  for (const raw of body.split('\n')) {
    const line = raw.trim()
    if (!line) continue
    const numbered = line.match(/^\d+\.\s*(.+)/)
    if (numbered) lines.push(numbered[1].trim())
    else if (line.includes('·')) lines.push(line)
  }
  const heading = result || title || '分子设计结果'
  if (lines.length > 0) {
    return `**${heading}**\n\n${lines.map((ln) => `- ${ln}`).join('\n')}`
  }
  return `**${heading}**\n\n${body}`
}

function formatLineListSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
  opts: { match: (blob: string) => boolean; heading: string },
): string | null {
  const title = (step.title || step.name || '').trim()
  const blob = `${title} ${step.name || ''}`.toLowerCase()
  if (!opts.match(blob)) return null
  const detail = stripProcessRuntimeNoise((step.detail || step.resultSummary || '').trim())
  if (!detail || isJsonLikeToolOutput(detail)) return null
  const lines = detail
    .split('\n')
    .map((ln) => ln.trim())
    .filter((ln) => ln && !isJsonLikeToolOutput(ln) && !isProcessDisplayNoise(ln))
  if (lines.length === 0) return null
  return `**${title || opts.heading}**\n\n${lines.map((ln) => `- ${ln}`).join('\n')}`
}

function formatTargetFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('靶点') || b.includes('target'),
    heading: '靶点发现结果',
  })
}

function formatProteinFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('蛋白质') || b.includes('protein'),
    heading: '蛋白质获取结果',
  })
}

function formatReceptorFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('受体') || b.includes('receptor'),
    heading: '受体准备结果',
  })
}

function formatDockingBoxFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('对接盒') || b.includes('docking_box') || b.includes('box config'),
    heading: '对接盒配置结果',
  })
}

function formatDockingFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) =>
      (b.includes('分子对接') || b.includes('molecular_docking') || b.includes('对接')) &&
      !b.includes('对接盒'),
    heading: '分子对接结果',
  })
}

function formatRetrosynthesisFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('逆合成') || b.includes('retrosynth'),
    heading: '逆合成分析结果',
  })
}

function formatConformerFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('构象') || b.includes('conformer'),
    heading: '3D 构象生成结果',
  })
}

function formatLigandFinalSection(
  step: Pick<ProcessStep, 'title' | 'name' | 'resultSummary' | 'detail'>,
): string | null {
  return formatLineListSection(step, {
    match: (b) => b.includes('配体') || b.includes('ligand'),
    heading: '配体准备结果',
  })
}

function extractField(block: string, field: string): string {
  const re = new RegExp(`^-\\s*${field}:\\s*`, 'm')
  const m = block.match(re)
  if (!m || m.index === undefined) return ''
  const start = m.index + m[0].length
  const rest = block.slice(start)
  const nextField = rest.search(/\n-\s*\S/)
  const value = nextField >= 0 ? rest.slice(0, nextField) : rest
  return value.trim()
}

function normalizeType(raw: string): ProcessStep['type'] {
  const t = raw.replace(/\s/g, '')
  if (t.includes('技能')) return '技能'
  if (t.includes('mcp')) return '工具'
  if (t.includes('搜索')) return '工具'
  if (t.includes('工具') && !t.includes('思考')) return '工具'
  if (t.includes('思考')) return '思考'
  return '未知'
}

function extractBestFinalAnswer(raw: string): string {
  const markers = ['## 最终回答', '##最终回答'] as const
  const sectionMarkers = ['## 最终回答', '##最终回答', '## 分析过程', '##分析过程'] as const
  const segments: string[] = []

  const sliceFinalSegment = (body: string): string => {
    let cut = body
    for (const marker of sectionMarkers) {
      const pos = cut.indexOf(marker)
      if (pos > 0) cut = cut.slice(0, pos)
    }
    cut = cut.trim()
    const noiseIdx = cut.search(/\n⚠️/)
    if (noiseIdx >= 0) cut = cut.slice(0, noiseIdx).trim()
    return cut
  }

  for (const marker of markers) {
    let start = 0
    while (true) {
      const pos = raw.indexOf(marker, start)
      if (pos < 0) break
      const body = sliceFinalSegment(raw.slice(pos + marker.length))
      if (body) segments.push(body)
      start = pos + marker.length
    }
  }
  const cleaned = segments.filter((s) => s && !isFinalAnswerUnusable(s))
  if (cleaned.length > 0) return cleaned[cleaned.length - 1]
  const trailing = extractTrailingModelFinal(raw)
  if (trailing) return trailing
  return segments.length > 0 ? segments[segments.length - 1] : ''
}

export function parseProcessLog(content: string): ParsedAssistantReply {
  const raw = content.trim()
  const procIdx = raw.indexOf('## 分析过程')
  const finalIdx = raw.indexOf('## 最终回答')

  if (procIdx === -1 || finalIdx === -1 || finalIdx <= procIdx) {
    const finalAnswer = extractBestFinalAnswer(raw) || extractTrailingModelFinal(raw)
    if (procIdx >= 0) {
      const processEnd =
        finalAnswer && raw.includes(finalAnswer)
          ? raw.indexOf(finalAnswer)
          : raw.length
      const processBlock = raw.slice(procIdx + '## 分析过程'.length, processEnd).trim()
      const toolCountMatch = processBlock.match(/工具数:\s*(\d+)/)
      const toolCount = toolCountMatch ? parseInt(toolCountMatch[1], 10) : 0
      const stepBlocks = [
        ...processBlock.matchAll(/###\s*步骤\s*(\d+)\s*·\s*(.+)\n([\s\S]*?)(?=###\s*步骤|\s*$)/g),
      ]
      const steps: ProcessStep[] = stepBlocks.map((m) => {
        const body = m[3]
        return {
          index: parseInt(m[1], 10),
          title: m[2].trim(),
          type: normalizeType(extractField(body, '类型')),
          status: extractField(body, '状态') || '已执行',
          name: extractField(body, '名称') || m[2].trim(),
          inputSummary: extractField(body, '输入摘要') || '',
          resultSummary: extractField(body, '结果摘要') || '',
          detail: extractField(body, '详情') || '',
        }
      })
      return { hasProcess: true, toolCount, steps, finalAnswer, raw }
    }
    if (finalAnswer) {
      return { hasProcess: false, toolCount: 0, steps: [], finalAnswer, raw }
    }
    return { hasProcess: false, toolCount: 0, steps: [], finalAnswer: raw, raw }
  }

  const processBlock = raw.slice(procIdx + '## 分析过程'.length, finalIdx).trim()
  let finalAnswer = extractBestFinalAnswer(raw.slice(finalIdx))
  if (!finalAnswer) {
    finalAnswer = raw.slice(finalIdx + '## 最终回答'.length).trim()
  }
  // strip trailing exec noise sometimes appended by tools
  const noiseIdx = finalAnswer.search(/\n⚠️\s*🛠️\s*Exec failed:/)
  if (noiseIdx >= 0) finalAnswer = finalAnswer.slice(0, noiseIdx).trim()

  const toolCountMatch = processBlock.match(/工具数:\s*(\d+)/)
  const toolCount = toolCountMatch ? parseInt(toolCountMatch[1], 10) : 0

  const stepBlocks = [...processBlock.matchAll(/###\s*步骤\s*(\d+)\s*·\s*(.+)\n([\s\S]*?)(?=###\s*步骤|\s*$)/g)]

  const steps: ProcessStep[] = stepBlocks.map((m) => {
    const body = m[3]
    return {
      index: parseInt(m[1], 10),
      title: m[2].trim(),
      type: normalizeType(extractField(body, '类型')),
      status: extractField(body, '状态'),
      name: extractField(body, '名称'),
      inputSummary: extractField(body, '输入摘要'),
      resultSummary: extractField(body, '结果摘要'),
      detail: extractField(body, '详情'),
    }
  })

  return {
    hasProcess: true,
    toolCount: Number.isFinite(toolCount)
      ? toolCount
      : steps.filter((s) => s.type === '工具' || s.type === '技能').length,
    steps,
    finalAnswer,
    raw,
  }
}

function isFailedStepResult(resultSummary: string, detail: string): boolean {
  const blob = stripProcessRuntimeNoise(`${resultSummary}\n${detail}`).trim()
  if (!blob) return true
  const failures = [
    '接口调用失败',
    '命令执行失败',
    '命令未执行',
    '工作目录不可用',
    '执行失败',
    '搜索未完成',
    'PDB ID 应为',
    'RCSB 未找到数据',
    '未解析到分辨率',
    '分子设计失败',
    '未找到有效口袋',
    'Molecule design failed',
  ]
  return failures.some((token) => blob.includes(token))
}

/** Step fields used for summary blocks above the process panel. */
export type SummaryStep = Pick<
  ProcessStep,
  'type' | 'title' | 'name' | 'resultSummary' | 'detail'
> & {
  /** Backend skill_display markdown; preferred over client-side parsing. */
  displayBlock?: string
}

/** 单步工具/技能 → 框上方摘要块（统一入口，避免各工具各写一套）。 */
export function formatActionStepSummaryBlock(step: SummaryStep): string | null {
  const prebuilt = (step.displayBlock || '').trim()
  if (prebuilt) {
    if (isProcessDisplayNoise(prebuilt)) return null
    return prebuilt
  }
  if (step.type !== '工具' && step.type !== '技能') return null
  if (isAuxiliaryToolStep(step)) return null
  for (const formatter of [
    formatMoleculeDesignFinalSection,
    formatTargetFinalSection,
    formatProteinFinalSection,
    formatPocketFinalSection,
    formatConformerFinalSection,
    formatReceptorFinalSection,
    formatLigandFinalSection,
    formatDockingBoxFinalSection,
    formatDockingFinalSection,
    formatAdmetFinalSection,
    formatRetrosynthesisFinalSection,
  ]) {
    const block = formatter(step)
    if (block) return block
  }
  const resultSummary = stripProcessRuntimeNoise((step.resultSummary || '').trim())
  const detail = stripProcessRuntimeNoise((step.detail || '').trim())
  if (isFailedStepResult(resultSummary, detail)) return null
  const body = (detail || resultSummary).trim()
  if (!body || body === '等待返回' || /^等待返回[。.!！]?$/.test(body) || isJsonLikeToolOutput(body) || isProcessDisplayNoise(body)) {
    return null
  }
  const heading = normalizeAi4DrugToolLabel(step.title || step.name || '结果')
  return `**${heading}**\n\n${body}`
}

/** Build a final-answer block from tool step outputs when the model omitted one. */
export function buildFallbackFinalAnswer(steps: SummaryStep[]): string {
  const parts: string[] = []
  const seen = new Set<string>()
  for (const step of steps) {
    const block = formatActionStepSummaryBlock(step)
    if (!block || seen.has(block)) continue
    seen.add(block)
    parts.push(block)
  }
  return parts.join('\n\n')
}

/** Final display: model stream wins; steps only as fallback (no merge duplication). */
export function resolveDisplayAnswer(
  parsed: Pick<ParsedAssistantReply, 'hasProcess' | 'finalAnswer' | 'raw'>,
  steps: SummaryStep[],
): string {
  const rawFinal = parsed.finalAnswer || (!parsed.hasProcess ? parsed.raw : '')
  const modelFinal = sanitizeFinalAnswerText(rawFinal)
  if (modelFinal && !isFinalAnswerUnusable(modelFinal)) {
    return modelFinal
  }
  return buildFallbackFinalAnswer(steps)
}

export function collectPdbIdsFromProcessSteps(
  steps: Pick<ProcessStep, 'title' | 'name' | 'inputSummary' | 'resultSummary' | 'detail'>[],
): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const step of steps) {
    const blob = `${step.title} ${step.name} ${step.inputSummary} ${step.resultSummary} ${step.detail}`
    for (const m of blob.matchAll(/\b([1-9][A-Z0-9]{3})\b/gi)) {
      const id = m[1].toUpperCase()
      if (!isValidPdbId(id) || seen.has(id)) continue
      seen.add(id)
      out.push(id)
    }
  }
  return out
}
