import type { LiveProcessStep } from '../api/client'
import { isJsonLikeToolOutput } from './processStepUtils'

function pickDisplayField(next?: string, prev?: string): string {
  if (next && !isJsonLikeToolOutput(next)) return next
  if (prev && !isJsonLikeToolOutput(prev)) return prev
  return ''
}

function longerText(a?: string, b?: string): string {
  const left = a || ''
  const right = b || ''
  return right.length > left.length ? right : left
}

export function resolveStepStatus(
  prev?: LiveProcessStep['status'],
  next?: LiveProcessStep['status'],
): LiveProcessStep['status'] {
  if (prev === 'failed' || next === 'failed') return 'failed'
  if (next) return next
  if (prev) return prev
  return 'done'
}

/** Merge streaming step updates; tool results attach by tool_call_id. */
export function mergeProcessStep(steps: LiveProcessStep[], step: LiveProcessStep): LiveProcessStep[] {
  const next = [...steps]
  if (step.is_result_update && step.tool_call_id) {
    const idx = next.findIndex((s) => s.tool_call_id === step.tool_call_id)
    if (idx >= 0) {
      const prev = next[idx]
      const generic = new Set(['exec', '执行命令', '命令工具', 'tool', 'bash', 'shell'])
      const name =
        step.name && !generic.has(step.name) ? step.name : prev.name || step.name
      const title =
        step.title && !generic.has(step.title) ? step.title : prev.title || step.title
      next[idx] = {
        ...prev,
        ...step,
        name,
        title,
        status: resolveStepStatus(prev.status, step.status),
        result: pickDisplayField(step.result, prev.result),
        detail: pickDisplayField(step.detail, prev.detail),
        input: pickDisplayField(step.input, prev.input),
      }
      return next
    }
  }
  if (step.tool_call_id) {
    const idx = next.findIndex((s) => s.tool_call_id === step.tool_call_id)
    if (idx >= 0) {
      const prev = next[idx]
      next[idx] = {
        ...prev,
        ...step,
        status: resolveStepStatus(prev.status, step.status),
        result: pickDisplayField(step.result, prev.result),
        detail: pickDisplayField(step.detail, prev.detail),
        input: pickDisplayField(step.input, prev.input),
      }
      return next
    }
  }
  if (step.record_id) {
    const seq = step.thinking_seq
    const idx = next.findIndex((s) => {
      if (s.record_id !== step.record_id || s.kind !== step.kind) return false
      if (step.kind === 'thinking' && seq != null) return s.thinking_seq === seq
      return true
    })
    if (idx >= 0) {
      const prev = next[idx]
      if (step.kind === 'thinking') {
        next[idx] = {
          ...prev,
          ...step,
          detail: longerText(prev.detail, step.detail),
          result: longerText(prev.result, step.result),
          input: longerText(prev.input, step.input),
        }
      } else {
        next[idx] = {
          ...prev,
          ...step,
          result: pickDisplayField(step.result, prev.result),
          detail: pickDisplayField(step.detail, prev.detail),
          input: pickDisplayField(step.input, prev.input),
        }
      }
      return next
    }
  }
  next.push(step)
  return next
}
