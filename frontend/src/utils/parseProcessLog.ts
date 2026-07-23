import { isValidPdbId } from './processStepUtils'

export type ProcessStep = {
  index: number
  title: string
  type: '思考' | '工具' | '技能' | '搜索' | '未知'
  status: string
  name: string
  inputSummary: string
  resultSummary: string
  detail: string
}

export type ParsedAssistantReply = {
  hasProcess: boolean
  toolCount: number
  steps: ProcessStep[]
  finalAnswer: string
  raw: string
}

/** Model sometimes dumps a collapsed process template instead of real results. */
export function isLowQualityFinalAnswer(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return true
  const compact = t.replace(/\s/g, '')
  if (compact.includes('##分析过程') || compact.includes('###步骤')) return true
  if (
    ['-类型:', '- 类型:', '等待执行', '状态:进行中', '状态:等待', '-状态:进行中', '-状态:等待'].some(
      (token) => t.includes(token),
    )
  ) {
    return true
  }
  if (
    (t.match(/✅/g) || []).length >= 2 &&
    !['QED', '评分', 'pocket', 'PDB', '|', '对接', 'hERG', 'BBB'].some((m) => t.includes(m))
  ) {
    return true
  }
  return false
}

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
  if (!detail) return null
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

function extractField(block: string, field: string): string {
  const re = new RegExp(`^-\\s*${field}:\\s*(.*)$`, 'm')
  const m = block.match(re)
  return m ? m[1].trim() : ''
}

function normalizeType(raw: string): ProcessStep['type'] {
  const t = raw.replace(/\s/g, '')
  if (t.includes('技能')) return '技能'
  if (t.includes('搜索')) return '工具'
  if (t.includes('工具') && !t.includes('思考')) return '工具'
  if (t.includes('思考')) return '思考'
  return '未知'
}

export function parseProcessLog(content: string): ParsedAssistantReply {
  const raw = content.trim()
  const procIdx = raw.indexOf('## 分析过程')
  const finalIdx = raw.indexOf('## 最终回答')

  if (procIdx === -1 || finalIdx === -1 || finalIdx <= procIdx) {
    return { hasProcess: false, toolCount: 0, steps: [], finalAnswer: raw, raw }
  }

  const processBlock = raw.slice(procIdx + '## 分析过程'.length, finalIdx).trim()
  let finalAnswer = raw.slice(finalIdx + '## 最终回答'.length).trim()
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
  const blob = `${resultSummary}\n${detail}`.trim()
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

/** Build a final-answer block from tool step outputs when the model omitted one. */
export function buildFallbackFinalAnswer(
  steps: Pick<ProcessStep, 'type' | 'title' | 'name' | 'resultSummary' | 'detail'>[],
): string {
  const parts: string[] = []
  const seen = new Set<string>()
  for (const step of steps) {
    if (step.type !== '工具' && step.type !== '技能') continue
    const admetBlock = formatAdmetFinalSection(step)
    if (admetBlock && !seen.has(admetBlock)) {
      seen.add(admetBlock)
      parts.push(admetBlock)
      continue
    }
    const resultSummary = (step.resultSummary || '').trim()
    const detail = (step.detail || '').trim()
    if (isFailedStepResult(resultSummary, detail)) continue
    const body = (detail || resultSummary).trim()
    if (!body || seen.has(body)) continue
    seen.add(body)
    const heading = (step.title || step.name || '结果').trim()
    parts.push(`**${heading}**\n\n${body}`)
  }
  return parts.join('\n\n')
}

/** Pick displayable final answer: ignore low-quality model text, fall back to step synthesis. */
export function resolveDisplayAnswer(
  parsed: Pick<ParsedAssistantReply, 'hasProcess' | 'finalAnswer' | 'raw'>,
  steps: Pick<ProcessStep, 'type' | 'title' | 'name' | 'resultSummary' | 'detail'>[],
): string {
  const rawFinal = parsed.finalAnswer || (!parsed.hasProcess ? parsed.raw : '')
  const finalAnswer = isLowQualityFinalAnswer(rawFinal) ? '' : rawFinal
  return finalAnswer.trim() || buildFallbackFinalAnswer(steps)
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
