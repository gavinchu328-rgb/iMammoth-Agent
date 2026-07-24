import type { ProcessLogSnapshot } from '../api/client'
import { hasReplyReady } from './liveActivity'
import { isLowQualityFinalAnswer, parseProcessLog } from './parseProcessLog'

export const RESUME_INCOMPLETE_ERROR =
  '对话恢复未完成，请刷新页面重试；分析过程步骤仍可在上方查看'

export const RESUME_PARTIAL_WARNING =
  '最终回答尚未生成，分析过程已保留；请刷新页面重试'

/** Try to resolve a final assistant reply without tailing the log stream. */
export function extractReplyFromSnapshot(
  snap: ProcessLogSnapshot,
  content = snap.content || '',
): string | null {
  const steps = snap.steps ?? []
  const hasRunning = steps.some((s) => s.status === 'running')

  if (hasReplyReady(content) && !hasRunning && snap.done) {
    const parsed = parseProcessLog(content)
    const reply = parsed.hasProcess ? content : parsed.finalAnswer
    if (reply.trim()) return reply
  }

  if (snap.done && snap.reply?.trim()) {
    return snap.reply
  }

  return null
}

export function shouldResumeInProgress(snap: ProcessLogSnapshot, awaitingReply: boolean): boolean {
  return Boolean(snap.in_progress && awaitingReply)
}

/** Process-log reply is richer than DB message (healed from raw stream). */
export function shouldPreferProcessLogReply(dbContent: string, healedReply: string): boolean {
  const db = (dbContent || '').trim()
  const healed = (healedReply || '').trim()
  if (!healed) return false
  if (!db) return true
  const dbFinal = parseProcessLog(db).finalAnswer || db
  const healFinal = parseProcessLog(healed).finalAnswer || healed
  if (isLowQualityFinalAnswer(dbFinal) && !isLowQualityFinalAnswer(healFinal)) return true
  return healFinal.length > dbFinal.length + 80
}
