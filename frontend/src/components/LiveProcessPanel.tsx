import { useMemo, useState } from 'react'
import type { LiveProcessStep } from '../api/client'
import AssistantMarkdown from './AssistantMarkdown'
import PdbStructureCards, { PdbCardsFromStepText } from './PdbStructureCards'
import {
  deriveLiveActivity,
  hasReplyReady,
} from '../utils/liveActivity'
import { buildFallbackFinalAnswer, collectPdbIdsFromProcessSteps, isLowQualityFinalAnswer } from '../utils/parseProcessLog'
import {
  formatStepStatusLine,
  isActionStep,
  isPdbRelatedStep,
  stepBadgeClass,
  stepBadgeLabel,
  stripProcessPaths,
} from '../utils/processStepUtils'
import { sortStepsForDisplay } from '../utils/sortSteps'

interface Props {
  steps: LiveProcessStep[]
  content?: string
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

function thinkingBody(step: LiveProcessStep): string {
  return stripProcessPaths(step.detail || step.result || step.input || step.title || '')
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
  return (
    <div className="flex items-start gap-2.5 text-sm">
      <PulseDot active={executing} />
      <div className="min-w-0 flex-1">
        <p
          className={`font-medium leading-snug ${executing ? 'text-[#1d6fbf]' : 'text-emerald-700'}`}
        >
          {activity.title}
        </p>
      </div>
    </div>
  )
}

export default function LiveProcessPanel({
  steps,
  content,
  skillName,
  showActivity = true,
}: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  const activity = useMemo(
    () => deriveLiveActivity(steps, skillName, { replyReady: hasReplyReady(content || '') }),
    [steps, skillName, content],
  )
  const replyReady = hasReplyReady(content || '')
  const displayContent =
    content && !isLowQualityFinalAnswer(content) ? content : replyReady ? '' : content
  const executing = showActivity
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
      })),
    [displaySteps],
  )
  const pdbIds = useMemo(() => collectPdbIdsFromProcessSteps(resultSteps), [resultSteps])
  const fallbackAnswer = useMemo(() => buildFallbackFinalAnswer(resultSteps), [resultSteps])

  const actionCount = displaySteps.filter((s) => isActionStep(s.kind)).length
  const skillCount = displaySteps.filter((s) => s.kind === 'skill').length
  const thinkCount = displaySteps.length - actionCount
  const header =
    skillCount > 0
      ? `分析过程 · ${displaySteps.length} 步（思考 ${thinkCount} · 技能 ${skillCount} · 工具 ${actionCount - skillCount}）`
      : thinkCount > 0
        ? `分析过程 · ${displaySteps.length} 步（思考 ${thinkCount} · 工具 ${actionCount}）`
        : `分析过程 · ${actionCount} 个工具`

  return (
    <div className="flex min-h-0 flex-col">
      <div className="min-h-0 flex-1 space-y-4">
        {displayContent && (
          <div className="assistant-prose text-[15px] leading-relaxed text-slate-800">
            <AssistantMarkdown>{displayContent}</AssistantMarkdown>
          </div>
        )}

        {displaySteps.length > 0 && (
          <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white/80">
            <div className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800">
              <span>{header}</span>
              <span className="text-xs font-normal text-emerald-600">
                {replyReady ? '已完成' : '实时更新中'}
              </span>
            </div>
            <div className="space-y-2 border-t border-slate-100 px-3 py-3">
              {displaySteps.map((step, i) => {
                const input = stripProcessPaths(step.input || '')
                const result = stripProcessPaths(step.result || '')
                const detail = stripProcessPaths(step.detail || '')
                const isRunning = step.status === 'running' && !replyReady
                const isThinking = step.kind === 'thinking'
                const stepKey = `${i}-${step.tool_call_id || step.record_id || step.kind}-${step.title || ''}`
                const isExpanded = expanded[stepKey] ?? false
                const showPdb = isPdbRelatedStep(step) && !isRunning
                // 避免把整段 JSON 结果再铺一遍
                const looksJson = /^[\s{[]/.test(result) || result.includes('"success"')
                const resultLine = looksJson ? '' : result.length > 120 ? `${result.slice(0, 117)}…` : result
                const detailLine =
                  looksJson && !detail
                    ? ''
                    : detail.length > 280
                      ? `${detail.slice(0, 277)}…`
                      : detail

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
                          <p className="leading-relaxed whitespace-pre-wrap">{thinkingBody(step)}</p>
                        ) : (
                          <p className="leading-snug whitespace-pre-wrap">
                            {`${formatStepStatusLine(step, { replyReady })}${
                              input && !input.includes('mcporter') ? ` · ${input}` : ''
                            }`}
                          </p>
                        )}
                        {!isThinking && resultLine && (
                          <p className="mt-1 text-xs text-slate-500">{resultLine}</p>
                        )}
                      </div>
                      {isRunning ? (
                        <span className="shrink-0 animate-pulse text-xs font-medium text-[#4BA4F8]">
                          进行中
                        </span>
                      ) : (
                        <span className="shrink-0 text-xs text-emerald-600">
                          {step.status === 'failed' ? '失败' : '完成'}
                        </span>
                      )}
                    </button>
                    {isExpanded && !isThinking && (detailLine || showPdb) && (
                      <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-600">
                        {detailLine && (
                          <div className="whitespace-pre-wrap rounded bg-white/80 px-2 py-1.5">{detailLine}</div>
                        )}
                        {showPdb && (
                          <PdbCardsFromStepText
                            title={step.title}
                            name={step.name}
                            input={input}
                            result={result}
                            detail={detail}
                          />
                        )}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>

      {replyReady && pdbIds.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-slate-800">检索到的蛋白结构</h4>
          <PdbStructureCards pdbIds={pdbIds} />
        </div>
      )}

      {replyReady && !displayContent?.trim() && fallbackAnswer && (
        <div className="assistant-prose text-[15px] leading-relaxed text-slate-800">
          <AssistantMarkdown>{fallbackAnswer}</AssistantMarkdown>
        </div>
      )}

      {showActivity && (
        <div className="sticky bottom-0 z-10 -mx-1 mt-3 border-t border-slate-200/80 bg-slate-50/95 px-1 pt-3 backdrop-blur-sm">
          <ActivityFooter
            activity={activity}
            executing={executing}
          />
        </div>
      )}
    </div>
  )
}
