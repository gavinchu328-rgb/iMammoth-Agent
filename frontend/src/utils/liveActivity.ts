import type { LiveProcessStep } from '../api/client'
import { hasExplicitFinalMarker, isStreamingFinalReady } from './streamingDisplay'
import { formatExecutedToolLabel, isActionStep } from './processStepUtils'

function stripPaths(text: string): string {
  return text
    .replace(/(?:~|\/home\/|\/data\d?\/|\/tmp\/|\.\/)[^\s"']+/g, (p) => {
      const base = p.replace(/\/+$/, '').split('/').pop()
      return base || '文件'
    })
    .trim()
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m} 分 ${s} 秒` : `${m} 分钟`
}

export interface LiveActivity {
  title: string
  detail: string
  runningStepIndex: number | null
  phase: LiveActivityPhase
}

export type LiveActivityPhase = 'running' | 'formatting' | 'idle'

export interface LiveActivityOptions {
  /** Stream has entered final-answer phase (live panel: tail wait before finalize). */
  streamFinalReady?: boolean
}

export function hasRunningProcessSteps(steps: LiveProcessStep[]): boolean {
  return steps.some((s) => isStepInProgress(s))
}

function isRuntimeWaitStep(step: LiveProcessStep): boolean {
  const blob = `${step.result || ''} ${step.detail || ''}`
  return /仍在后台|仍在运行|command still running|process still running/i.test(blob)
}

export function isStepInProgress(step: LiveProcessStep): boolean {
  if (step.status === 'running') return true
  return isRuntimeWaitStep(step)
}

function findActiveStepIndex(steps: LiveProcessStep[]): number {
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    if (isStepInProgress(steps[i])) return i
  }
  return -1
}

export function hasReplyReady(content: string): boolean {
  return isStreamingFinalReady(content)
}

function hasCompletedActionSteps(steps: LiveProcessStep[]): boolean {
  return steps.some(
    (s) =>
      (s.kind === 'tool' || s.kind === 'skill') &&
      s.status !== 'running' &&
      !isRuntimeWaitStep(s),
  )
}

/** Stream final is ready and no tool is still running. */
export function isAnalysisComplete(content: string, steps: LiveProcessStep[]): boolean {
  if (!hasReplyReady(content) || hasRunningProcessSteps(steps)) return false
  if (hasExplicitFinalMarker(content)) return true
  // 无明确「最终回答」标记时，须至少完成一个工具/技能步骤，避免前言触发过早 finalize
  return hasCompletedActionSteps(steps)
}

/** Stream final is ready (display and/or raw SSE buffer). */
export function isStreamPhaseComplete(content: string, streamRaw?: string): boolean {
  return hasReplyReady(content) || hasReplyReady(streamRaw || '')
}

/** Live panel tail: stream ended, waiting for backend finalize / page switch. */
export function isLivePanelTailFormatting(
  content: string,
  steps: LiveProcessStep[],
  options?: { streamRaw?: string; awaitingFinalize?: boolean },
): boolean {
  if (hasRunningProcessSteps(steps)) return false
  if (isStreamPhaseComplete(content, options?.streamRaw)) return true
  const raw = (options?.streamRaw || '').trim()
  if (options?.awaitingFinalize && raw && (raw.includes('## 最终回答') || raw.includes('##最终回答'))) {
    return true
  }
  return false
}

export function deriveLiveActivityPhase(
  steps: LiveProcessStep[],
  options?: LiveActivityOptions,
): LiveActivityPhase {
  if (hasRunningProcessSteps(steps)) return 'running'
  if (options?.streamFinalReady) return 'formatting'
  return 'idle'
}

export function deriveLiveActivity(
  steps: LiveProcessStep[],
  skillName?: string,
  options?: LiveActivityOptions,
): LiveActivity {
  const phase = deriveLiveActivityPhase(steps, options)
  const runningIdx = findActiveStepIndex(steps)
  const running = runningIdx >= 0 ? steps[runningIdx] : undefined

  if (phase === 'running' && running && isActionStep(running)) {
    const label = formatExecutedToolLabel(running)
    const input = stripPaths(running.input || '')
    const prefix = running.kind === 'skill' ? '正在执行技能' : '正在执行'
    return {
      title: `${prefix}：${label}`,
      detail: input ? `参数 ${input}` : running.kind === 'skill' ? '技能运行中…' : '请稍候…',
      runningStepIndex: runningIdx,
      phase,
    }
  }

  if (phase === 'running' && running?.kind === 'thinking') {
    const text = stripPaths(running.result || running.input || '')
    return {
      title: skillName ? `猛犸智能体正在分析（${skillName}）` : '猛犸智能体正在分析',
      detail: text ? text.slice(0, 80) : '整理思路中…',
      runningStepIndex: runningIdx,
      phase,
    }
  }

  if (phase === 'formatting') {
    return {
      title: '正在整理最终结果',
      detail: '',
      runningStepIndex: null,
      phase,
    }
  }

  if (skillName) {
    return {
      title: `猛犸智能体正在处理：${skillName}`,
      detail: '',
      runningStepIndex: null,
      phase,
    }
  }

  return {
    title: '猛犸智能体正在思考',
    detail: '分析问题并选择合适工具…',
    runningStepIndex: null,
    phase,
  }
}
