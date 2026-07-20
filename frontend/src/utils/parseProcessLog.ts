export type ProcessStep = {
  index: number
  title: string
  type: '思考' | '工具' | '未知'
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

function extractField(block: string, field: string): string {
  const re = new RegExp(`^-\\s*${field}:\\s*(.*)$`, 'm')
  const m = block.match(re)
  return m ? m[1].trim() : ''
}

function normalizeType(raw: string): ProcessStep['type'] {
  const t = raw.replace(/\s/g, '')
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
    toolCount: Number.isFinite(toolCount) ? toolCount : steps.filter((s) => s.type === '工具').length,
    steps,
    finalAnswer,
    raw,
  }
}
