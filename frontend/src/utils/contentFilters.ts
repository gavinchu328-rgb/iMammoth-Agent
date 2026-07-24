/** Process vs final answer filtering — keep rules separate. */

export function hasRichMarkdownReport(text: string): boolean {
  const t = (text || '').trim()
  if (t.length < 120) return false
  const headers = (t.match(/^#{1,6}\s+\S/gm) || []).length
  const hasTable = t.includes('|') && t.includes('---')
  if (headers >= 2 && hasTable) return true
  if (headers >= 1 && hasTable && t.length >= 200) return true
  return false
}

export function isProcessTemplateDump(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return true
  const compact = t.replace(/\s/g, '')
  if (compact.includes('##分析过程') || compact.includes('###步骤')) return true
  if (
    ['-类型:', '- 类型:', '等待执行', '等待返回', '状态:进行中', '状态:等待', '-状态:进行中', '-状态:等待'].some(
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

export function isSynthesizedStepDumpFinal(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  const fieldHits = (t.match(/^-\s*(?:输入摘要|结果摘要|详情):/gm) || []).length
  if (fieldHits >= 2) return true
  if (
    t.includes('逆合成路线已生成') &&
    (t.includes('未能找到') || t.includes('no synthesis routes') || t.includes('MCP 工具未能'))
  ) {
    return true
  }
  if (t.startsWith('**3D构象生成**') && t.includes('逆合成路线已生成')) return true
  return false
}

/** Final answer unusable → fall back to step synthesis only. */
export function isFinalAnswerUnusable(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return true
  if (isSynthesizedStepDumpFinal(t)) return true
  if (hasRichMarkdownReport(t)) return false
  if (isProcessTemplateDump(t)) return true
  if (t.includes('"pocket_id":') && !t.includes('|') && t.length < 200) return true
  if (t.includes('"molecules":') && !t.includes('|') && t.length < 200) return true
  return false
}

const EMOJI_BETWEEN = '(?:[\\u{1F300}-\\u{1FAFF}]|[\\u{2600}-\\u{27BF}])\\s*'

function stripOrphanEmojiLines(text: string): string {
  return (text || '')
    .split('\n')
    .filter((ln) => !/^\s*(?:[\u{1F300}-\u{1FAFF}]|[\u{2600}-\u{27BF}])+\s*$/u.test(ln))
    .join('\n')
}

export function stripStructuredJsonAppendix(text: string): string {
  let t = (text || '').trim()
  if (!t) return ''
  t = t
    .replace(
      new RegExp(
        `\\n*(?:#{1,3}\\s*)?${EMOJI_BETWEEN}(?:\\*{1,2})?完整结构化数据:?(?:\\*{1,2})?\\s*\\n*\`\`\`json\\s*[\\s\\S]*?\`\`\``,
        'giu',
      ),
      '',
    )
    .trim()
  t = t.replace(/\n*```json\s*\{[\s\S]*?"session_id"[\s\S]*?```\s*$/i, '').trim()
  t = t
    .replace(new RegExp(`\\n*#{1,3}\\s*${EMOJI_BETWEEN}完整结构化数据\\s*$`, 'giu'), '')
    .trim()
  return stripOrphanEmojiLines(t)
}

export function sanitizeFinalAnswerText(text: string): string {
  let t = (text || '').trim()
  if (!t) return ''
  const procIdx = t.search(/##\s*分析过程/)
  if (procIdx >= 0) t = t.slice(0, procIdx).trim()
  const noiseIdx = t.search(/\n⚠️/)
  if (noiseIdx >= 0) t = t.slice(0, noiseIdx).trim()
  const execIdx = t.indexOf('\n⚠️ 🛠️ Exec failed:')
  if (execIdx >= 0) t = t.slice(0, execIdx).trim()
  return stripStructuredJsonAppendix(t)
}

/** @deprecated Use isFinalAnswerUnusable */
export function isLowQualityFinalAnswer(text: string): boolean {
  return isFinalAnswerUnusable(text)
}

const TRAILING_FINAL_START =
  /(?:✅\s*\*\*第\s*\d+\s*步|✅\s*\*\*步骤\s*\d+|(?:^|\n)##\s*结果摘要|(?:^|\n)###\s*🔬|(?:^|\n)#\s+🔬|(?:^|\n)###\s*🫁)/m

function looksLikeLiveProcessChunk(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return true
  if (t.includes('### 步骤') && t.includes('- 类型:') && t.includes('- 状态:')) return true
  if (t.includes('- 工具数:') && t.includes('### 步骤')) return true
  return false
}

/** Model prose after embedded process when ## 最终回答 is missing. */
export function extractTrailingModelFinal(raw: string): string {
  const text = (raw || '').trim()
  if (!text) return ''

  const candidates: string[] = []
  const re = new RegExp(TRAILING_FINAL_START.source, TRAILING_FINAL_START.flags + 'g')
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const tail = sanitizeFinalAnswerText(text.slice(m.index))
    if (tail && !isProcessTemplateDump(tail) && !isFinalAnswerUnusable(tail)) {
      candidates.push(tail)
    }
  }
  if (candidates.length > 0) {
    return candidates.sort((a, b) => b.length - a.length)[0]
  }

  const parts = text.split(/##\s*分析过程|##分析过程/)
  const remainder = parts
    .map((p) => p.trim())
    .filter((p) => p && !looksLikeLiveProcessChunk(p) && !isProcessTemplateDump(p))
    .join('\n\n')
  const cleaned = sanitizeFinalAnswerText(remainder)
  if (cleaned && !isProcessTemplateDump(cleaned) && !isFinalAnswerUnusable(cleaned)) {
    return cleaned
  }
  return ''
}
