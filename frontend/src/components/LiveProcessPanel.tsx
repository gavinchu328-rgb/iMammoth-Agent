import { useEffect, useMemo, useRef, useState } from 'react'
import type { LiveProcessStep } from '../api/client'
import AssistantMarkdown from './AssistantMarkdown'
import {
  deriveLiveActivity,
  hasRunningProcessSteps,
  isLivePanelTailFormatting,
  isStreamPhaseComplete,
} from '../utils/liveActivity'
import { buildFallbackFinalAnswer, isLowQualityFinalAnswer } from '../utils/parseProcessLog'
import {
  looksLikeModelPipelineChecklist,
  looksLikePartialProcessStream,
  stripStreamingNoise,
} from '../utils/streamingDisplay'
import {
  formatStepStatusLine,
  formatToolOutputForDisplay,
  isJsonLikeToolOutput,
  stepBadgeClass,
  stepBadgeLabel,
  stripProcessPaths,
  thinkingFullText,
  thinkingSummaryLine,
} from '../utils/processStepUtils'
import { sortStepsForDisplay } from '../utils/sortSteps'
import {
  buildProcessPanelHeader,
  countProcessPanelSteps,
  getLiveActivityFooterClassName,
  getLiveStepListClassName,
  getLiveStreamContentClassName,
  getProcessPanelCardClassName,
  getProcessPanelHeaderRowClassName,
} from '../utils/processPanelLayout'

interface Props {
  steps: LiveProcessStep[]
  content?: string
  /** Full SSE buffer; used to detect ## 最终回答 when display content is stripped. */
  streamRaw?: string
  /** Chat still awaiting onDone / finalize. */
  awaitingFinalize?: boolean
  skillName?: string
  showActivity?: boolean
}

function StepBadge({ kind, name, title }: { kind: LiveProcessStep['kind']; name?: string; title?: string }) {
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${stepBadgeClass(kind, name, title)}`}
    >
      {stepBadgeLabel(kind, name, title)}
    </span>
  )
}

function PulseDot({ active = true }: { active?: boolean }) {
  if (!active) {
    return <span className="mt-0.5 h-3 w-3 shrink-0 rounded-full bg-emerald-500" />
  }
  return (
    <span className="relative mt-0.5 flex h-3 w-3 shrink-0">
      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[#4BA4F8] opacity-75" />
      <span className="relative inline-flex h-3 w-3 rounded-full bg-[#4BA4F8]" />
    </span>
  )
}

function ActivityFooter({
  activity,
  executing,
}: {
  activity: ReturnType<typeof deriveLiveActivity>
  executing: boolean
}) {
  const titleClass = executing ? 'text-[#1d6fbf]' : 'text-slate-700'

  return (
    <div className="flex items-start gap-2.5 text-sm">
      <PulseDot active={executing} />
      <div className="min-w-0 flex-1">
        <p className={`font-medium leading-snug ${titleClass}`}>{activity.title}</p>
        {activity.detail ? (
          <p className="mt-0.5 text-xs leading-snug text-slate-500">{activity.detail}</p>
        ) : null}
      </div>
    </div>
  )
}

export default function LiveProcessPanel({
  steps,
  content,
  streamRaw,
  awaitingFinalize = false,
  skillName,
  showActivity = true,
}: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const streamFinalReady = isStreamPhaseComplete(content || '', streamRaw)
  const hasRunningSteps = hasRunningProcessSteps(steps)
  const isTailFormatting = isLivePanelTailFormatting(content || '', steps, {
    streamRaw,
    awaitingFinalize,
  })
  const displaySteps = useMemo(() => sortStepsForDisplay(steps), [steps])
  const resultSteps = useMemo(
    () =>
      displaySteps.map((step, i) => ({
        index: i + 1,
        title: step.title || step.name || '工具',
        type:
          step.kind === 'skill' ? ('技能' as const) : step.kind === 'thinking' ? ('思考' as const) : ('工具' as const),
        status: step.status || '已执行',
        name: step.name || '',
        inputSummary: stripProcessPaths(step.input || ''),
        resultSummary: stripProcessPaths(step.result || ''),
        detail: stripProcessPaths(step.detail || ''),
        displayBlock: (step.display_block || '').trim(),
      })),
    [displaySteps],
  )
  const fallbackAnswer = useMemo(() => buildFallbackFinalAnswer(resultSteps), [resultSteps])
  const summaryAbove = useMemo(() => {
    const fromStream =
      content && !isLowQualityFinalAnswer(content) ? content.trim() : streamFinalReady ? '' : (content || '').trim()
    if (streamFinalReady && !hasRunningSteps) {
      return fromStream || fallbackAnswer.trim() || ''
    }
    // 执行中（含对接盒等多步技能）：上方只展示模型流式正文，步骤摘要留给过程框，避免双层内容抢高度
    return fromStream
  }, [content, streamFinalReady, fallbackAnswer, hasRunningSteps])

  const summaryDisplay = useMemo(() => {
    const text = summaryAbove.trim()
    if (!text) return ''
    const cleaned = stripStreamingNoise(text)
    if (looksLikeModelPipelineChecklist(cleaned || text)) return ''
    // 过程面板已展示步骤时，不再重复显示模型流水线 checklist
    if (hasRunningSteps && displaySteps.length > 0 && (looksLikeModelPipelineChecklist(text) || !cleaned)) {
      return ''
    }
    if (cleaned) return cleaned
    if (looksLikePartialProcessStream(text)) return ''
    return text
  }, [summaryAbove, hasRunningSteps, displaySteps.length])

  const activity = useMemo(
    () => deriveLiveActivity(steps, skillName, { streamFinalReady: isTailFormatting }),
    [steps, skillName, isTailFormatting],
  )
  // Live 面板仅在整轮回复进行中展示；步骤间隙（idle）也应保持蓝色脉冲，避免误显示绿色完成态。
  const executing = showActivity
  const panelStatusLabel = isTailFormatting ? '整理最终结果中' : '实时更新中'
  const panelStatusClass = 'text-[#1d6fbf]'

  const stepCounts = useMemo(() => countProcessPanelSteps(displaySteps), [displaySteps])
  const header = useMemo(() => buildProcessPanelHeader(stepCounts), [stepCounts])

  const hasStreamAbove = Boolean(summaryDisplay)
  const stepListClass = getLiveStepListClassName({ hasStreamAbove, isTailFormatting })

  const stepListRef = useRef<HTMLDivElement>(null)
  const stepsScrollKey = useMemo(
    () =>
      displaySteps
        .map(
          (s) =>
            `${s.tool_call_id || s.record_id || ''}:${s.status}:${s.result?.length ?? 0}:${s.detail?.length ?? 0}`,
        )
        .join('|'),
    [displaySteps],
  )

  useEffect(() => {
    if (isTailFormatting) return
    const el = stepListRef.current
    if (!el) return
    const frame = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight
    })
    return () => cancelAnimationFrame(frame)
  }, [isTailFormatting, stepsScrollKey])

  return (
    <div className="flex min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-4">
        {summaryDisplay && (
          <div className={getLiveStreamContentClassName()}>
            <AssistantMarkdown>{summaryDisplay}</AssistantMarkdown>
          </div>
        )}

        {displaySteps.length > 0 && (
          <div className={getProcessPanelCardClassName()}>
            <div className={getProcessPanelHeaderRowClassName()}>
              <span className="min-w-0 truncate pr-2">{header}</span>
              <span className={`shrink-0 text-xs font-normal ${panelStatusClass}`}>{panelStatusLabel}</span>
            </div>

            <div ref={stepListRef} className={stepListClass}>
              {displaySteps.map((step, i) => {
                const input = stripProcessPaths(step.input || '')
                const result = formatToolOutputForDisplay(stripProcessPaths(step.result || ''))
                const detail = formatToolOutputForDisplay(stripProcessPaths(step.detail || ''))
                const isRunning = step.status === 'running' && hasRunningSteps
                const isThinking = step.kind === 'thinking'
                const thinkingFull = isThinking ? thinkingFullText(step) : ''
                const thinkingSummary = isThinking ? thinkingSummaryLine(thinkingFull) : ''
                const hasThinkingDetail =
                  isThinking &&
                  thinkingFull.replace(/\s+/g, ' ').trim().length >
                    thinkingSummary.replace(/…$/, '').trim().length + 8
                const stepKey = `${i}-${step.tool_call_id || step.record_id || step.kind}-${step.title || ''}`
                const isExpanded = expanded[stepKey] ?? false
                const looksJson = isJsonLikeToolOutput(stripProcessPaths(step.result || step.detail || ''))
                const resultLine = looksJson ? '' : result.length > 120 ? `${result.slice(0, 117)}…` : result

                return (
                  <div
                    key={stepKey}
                    className={`rounded-lg border px-3 py-2.5 transition-colors ${
                      isRunning
                        ? 'border-[#4BA4F8]/50 bg-[#4BA4F8]/8 ring-1 ring-[#4BA4F8]/25'
                        : 'border-slate-100 bg-slate-50/80'
                    }`}
                  >
                    <button
                      type="button"
                      className="flex w-full items-start gap-2 text-left text-sm text-slate-700"
                      onClick={() => setExpanded((prev) => ({ ...prev, [stepKey]: !isExpanded }))}
                    >
                      <span className="shrink-0 rounded bg-slate-200/80 px-1.5 py-0.5 text-[10px] font-medium text-slate-600">
                        步骤 {i + 1}
                      </span>
                      <StepBadge kind={step.kind} name={step.name} title={step.title} />
                      <div className="min-w-0 flex-1">
                        {isThinking ? (
                          <p className="leading-snug whitespace-pre-wrap">{thinkingSummary}</p>
                        ) : (
                          <p className="leading-snug whitespace-pre-wrap">
                            {`${formatStepStatusLine(step)}${
                              input && !input.includes('mcporter') ? ` · ${input}` : ''
                            }`}
                          </p>
                        )}
                        {!isThinking && resultLine && (
                          <p className="mt-1 text-xs whitespace-pre-wrap text-slate-500">{resultLine}</p>
                        )}
                      </div>
                      {isThinking ? (
                        hasThinkingDetail && (
                          <span className="shrink-0 text-xs text-slate-400">{isExpanded ? '▾' : '▸'}</span>
                        )
                      ) : isRunning ? (
                        <span className="shrink-0 animate-pulse text-xs font-medium text-[#4BA4F8]">
                          进行中
                        </span>
                      ) : (
                        <span className="shrink-0 text-xs text-emerald-600">
                          {step.status === 'failed' ? '失败' : '完成'}
                        </span>
                      )}
                    </button>
                    {isExpanded && isThinking && hasThinkingDetail && (
                      <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-600">
                        <div className="whitespace-pre-wrap rounded bg-white/80 px-2 py-1.5">{thinkingFull}</div>
                      </div>
                    )}
                    {isExpanded && !isThinking && detail && (
                      <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-600">
                        <div className="whitespace-pre-wrap rounded bg-white/80 px-2 py-1.5">{detail}</div>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {showActivity && (
        <div className={getLiveActivityFooterClassName()}>
          <ActivityFooter activity={activity} executing={executing} />
        </div>
      )}
    </div>
  )
}
