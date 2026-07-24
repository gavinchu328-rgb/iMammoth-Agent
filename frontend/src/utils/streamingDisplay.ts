import { isJsonLikeToolOutput } from './processStepUtils'
import { isFinalAnswerUnusable, sanitizeFinalAnswerText } from './contentFilters'

const PROCESS_MARKERS = ['## 分析过程', '##分析过程', '### 步骤', '###步骤'] as const
const FINAL_MARKERS = ['## 最终回答', '##最终回答'] as const

function findFirstMarker(text: string, markers: readonly string[]): number {
  let idx = -1
  for (const marker of markers) {
    const pos = text.indexOf(marker)
    if (pos >= 0 && (idx < 0 || pos < idx)) idx = pos
  }
  return idx
}

function looksLikeCollapsedProcessDump(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if (t.includes('工具数:') && (t.includes('步骤') || t.includes('###'))) return true
  if (/-\s*类型:\s*工具/.test(t) && t.includes('结果摘要')) return true
  if (t.includes('ai4drug__') && (t.includes('输入摘要') || t.includes('结果摘要'))) return true
  return false
}

const PIPELINE_TOOL_KEYS =
  /(?:molecular_docking|ligand_preparation|conformer_generation|pocket_prediction|receptor_preparation|protein_acquisition|docking_box_config|target_discovery|molecule_design|retrosynthesis|molecule_evaluation)/i

const SESSION_RETRY_MONOLOGUE =
  /发现\s*API\s*返回了自动生成的\s*session_id|需要用正确\s*session_id\s*重试|现在用正确的\s*session_id|第二个使用正确\s*session_id\s*的\s*conformer/i

const ORPHAN_EMOJI_ONLY = /^\s*(?:[\u{1F300}-\u{1FAFF}]|[\u{2600}-\u{27BF}])+\s*$/u

function looksLikeSessionRetryMonologue(text: string): boolean {
  return SESSION_RETRY_MONOLOGUE.test((text || '').trim())
}

/** Model sometimes streams an English pipeline checklist instead of real results. */
export function looksLikeModelPipelineChecklist(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if (/等待执行/.test(t)) return true
  // 分子对接等多步技能：带真实结果/报告链接的步骤摘要应保留流式展示
  if (/kcal\/mol|Docking Score|查看报告|ai4drug-reports/i.test(t)) return false
  if (/✅\s*\*\*步骤\s*\d+[：:][^\n*]+完成\*\*/.test(t) && t.length > 100) return false
  if (/✅\s*步骤\s*\d+\s*完成/.test(t) && !/http|kcal|评分|score|报告/i.test(t)) return true
  if (PIPELINE_TOOL_KEYS.test(t) && (t.includes('等待') || /步骤\s*\d+\s*完成/.test(t))) {
    return true
  }
  const lines = t
    .split('\n')
    .map((ln) => ln.trim())
    .filter(Boolean)
  const englishOnly = lines.filter((ln) => PIPELINE_TOOL_KEYS.test(ln) && ln.length < 48)
  if (englishOnly.length >= 1 && /等待执行/.test(t)) return true
  return false
}

/** Incomplete ## 分析过程 tokens while streaming (e.g. lone "分析" after "## "). */
export function looksLikePartialProcessStream(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return false
  if (/^#{1,3}\s*分析/.test(t)) return true
  if (/^#{1,3}分析/.test(t)) return true
  if (t === '分析' || t === '分析过程' || t.startsWith('分析过程')) return true
  if (/^#+\s*$/.test(t)) return true
  return false
}

export function looksLikeProcessDump(text: string): boolean {
  const t = (text || '').trim()
  if (!t) return true
  if (PROCESS_MARKERS.some((m) => t.includes(m))) return true
  if (looksLikePartialProcessStream(t)) return true
  if (looksLikeCollapsedProcessDump(t)) return true
  if (isJsonLikeToolOutput(t)) return true
  if (t.includes('"success"') && (t.includes('{') || t.includes('['))) return true
  return false
}

/** Remove embedded ### 步骤 tool-template blocks from multi-step stream narrative. */
export function stripEmbeddedProcessTemplateBlocks(text: string): string {
  let t = (text || '').trim()
  if (!t) return ''
  t = t
    .replace(/###\s*步骤\s*\d+\s*·[\s\S]*?(?=\n✅\s*(?:\*\*)?步骤|\n#{1,3}\s+|\n---\s*\n|\s*$)/g, '')
    .trim()
  t = t.replace(/^##\s*分析过程[\s\S]*?(?=\n✅\s*(?:\*\*)?步骤)/, '').trim()
  return t
}

function extractStepNarrativeStream(text: string): string {
  const stepIdx = text.search(/✅\s*(?:\*\*)?步骤\s*\d+/)
  if (stepIdx < 0) return ''
  let narrative = text.slice(stepIdx)
  const finalIdx = findFirstMarker(narrative, FINAL_MARKERS)
  if (finalIdx >= 0) {
    const marker = FINAL_MARKERS.find((m) => narrative.indexOf(m) === finalIdx) || FINAL_MARKERS[0]
    narrative = narrative.slice(0, finalIdx) + narrative.slice(finalIdx + marker.length)
  }
  narrative = stripEmbeddedProcessTemplateBlocks(narrative)
  narrative = sanitizeFinalAnswerText(narrative)
  if (!narrative || isFinalAnswerUnusable(narrative)) return ''
  if (looksLikeModelPipelineChecklist(narrative)) return ''
  return narrative
}

/** Strip model process templates / JSON from streaming assistant text. */
export function stripStreamingNoise(content: string): string {
  const raw = (content || '').trim()
  if (!raw) return ''
  if (/<tool_call/i.test(raw)) {
    return raw.replace(/<tool_call[\s\S]*?(<\/tool_call>|$)/gi, '').trim()
  }

  const finalIdx = findFirstMarker(raw, FINAL_MARKERS)
  if (finalIdx >= 0) {
    const marker = FINAL_MARKERS.find((m) => raw.indexOf(m) === finalIdx) || FINAL_MARKERS[0]
    let final = raw.slice(finalIdx + marker.length)
    const procInFinal = findFirstMarker(final, PROCESS_MARKERS)
    if (procInFinal >= 0) final = final.slice(0, procInFinal)
    final = sanitizeFinalAnswerText(final)
    if (final && !isFinalAnswerUnusable(final)) {
      return final
    }
    return ''
  }

  const stepNarrative = extractStepNarrativeStream(raw)
  if (stepNarrative) return stepNarrative

  let procIdx = findFirstMarker(raw, PROCESS_MARKERS)
  if (procIdx < 0 && looksLikeCollapsedProcessDump(raw)) procIdx = 0
  if (procIdx >= 0) {
    const preamble = sanitizeFinalAnswerText(raw.slice(0, procIdx).trim())
    return preamble && !isFinalAnswerUnusable(preamble) ? preamble : ''
  }

  if (looksLikeProcessDump(raw)) return ''
  if (looksLikePartialProcessStream(raw)) return ''
  if (looksLikeModelPipelineChecklist(raw)) return ''
  if (looksLikeSessionRetryMonologue(raw)) return ''
  if (ORPHAN_EMOJI_ONLY.test(raw)) return ''
  return raw
}

export function resolveStreamingDisplayContent(
  content: string | undefined,
  opts: { hasLiveSteps: boolean; parsedFinalAnswer?: string; hasProcess?: boolean },
): string | undefined {
  const raw = (content || '').trim()
  const cleaned = stripStreamingNoise(raw)

  const pickFinal = (text: string): string | undefined => {
    const t = sanitizeFinalAnswerText(text.trim())
    if (!t || isFinalAnswerUnusable(t)) return undefined
    return t
  }

  if (opts.hasLiveSteps) {
    // 步骤面板负责过程；正文只展示最终回答流（后端可能已剥掉 ## 标题）
    if (opts.hasProcess && opts.parsedFinalAnswer) {
      const fromParsed = pickFinal(opts.parsedFinalAnswer)
      if (fromParsed) return fromParsed
    }
    if (cleaned) return pickFinal(cleaned)
    if (!opts.hasProcess && opts.parsedFinalAnswer) {
      return pickFinal(stripStreamingNoise(opts.parsedFinalAnswer))
    }
    return undefined
  }

  return cleaned ? pickFinal(cleaned) : undefined
}

/** 流式正文是否已进入「最终回答」阶段（兼容后端剥掉 ## 标记的情况）。 */
export function hasExplicitFinalMarker(content: string): boolean {
  const raw = (content || '').trim()
  if (!raw) return false
  const finalIdx = findFirstMarker(raw, FINAL_MARKERS)
  if (finalIdx < 0) return false
  const marker = FINAL_MARKERS.find((m) => raw.indexOf(m) === finalIdx) || FINAL_MARKERS[0]
  return raw.slice(finalIdx + marker.length).trim().length >= 8
}

/** 流式正文是否已进入「最终回答」阶段（兼容后端剥掉 ## 标记的情况）。 */
export function isStreamingFinalReady(content: string): boolean {
  const raw = (content || '').trim()
  if (!raw) return false
  if (hasExplicitFinalMarker(raw)) return true
  const cleaned = sanitizeFinalAnswerText(stripStreamingNoise(raw))
  return cleaned.length >= 8 && !isFinalAnswerUnusable(cleaned)
}
