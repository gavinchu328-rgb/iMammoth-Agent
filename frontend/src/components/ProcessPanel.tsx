import { useMemo, useState } from 'react'
import type { LiveProcessStep } from '../api/client'
import type { ParsedAssistantReply, ProcessStep } from '../utils/parseProcessLog'
import { collectPdbIdsFromProcessSteps, resolveDisplayAnswer } from '../utils/parseProcessLog'
import { sortStepsForDisplay } from '../utils/sortSteps'
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
import {
  buildProcessPanelHeader,
  countProcessPanelSteps,
  getFinalStepListClassName,
  getProcessPanelCardClassName,
} from '../utils/processPanelLayout'
import AssistantMarkdown from './AssistantMarkdown'
import PdbStructureCards, { PdbCardsFromStepText } from './PdbStructureCards'

interface Props {
  parsed: ParsedAssistantReply
  liveSteps?: LiveProcessStep[]
}

function StepBadge({ type, name, title }: { type: ProcessStep['type']; name?: string; title?: string }) {
  const kind: LiveProcessStep['kind'] =
    type === '技能' ? 'skill' : type === '工具' ? 'tool' : 'thinking'
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${stepBadgeClass(kind, name, title)}`}
    >
      {stepBadgeLabel(kind, name, title)}
    </span>
  )
}

function liveToProcessSteps(live: LiveProcessStep[]): ProcessStep[] {
  return live.map((step, i) => ({
    index: i + 1,
    title: step.title || step.name || (step.kind !== 'thinking' ? '工具' : '深度思考'),
    type:
      step.kind === 'skill' ? '技能' : step.kind === 'thinking' ? '思考' : '工具',
    status: step.status === 'running' ? '进行中' : step.status === 'failed' ? '失败' : '已完成',
    name: step.name || '',
    inputSummary: stripProcessPaths(step.input || ''),
    resultSummary: stripProcessPaths(step.result || ''),
    detail: stripProcessPaths(step.detail || ''),
    displayBlock: (step.display_block || '').trim(),
  }))
}

function stepBodyLength(step: Pick<ProcessStep, 'detail' | 'resultSummary' | 'inputSummary'>): number {
  return (step.detail || step.resultSummary || step.inputSummary || '').length
}

function mergeDisplaySteps(parsed: ProcessStep[], live: ProcessStep[]): ProcessStep[] {
  if (!live.length) return parsed
  if (!parsed.length) return live
  const parsedHasThinking = parsed.some((s) => s.type === '思考')
  const liveHasThinking = live.some((s) => s.type === '思考')
  if (live.length > parsed.length || (liveHasThinking && !parsedHasThinking)) {
    return live.map((s, i) => ({ ...s, index: i + 1 }))
  }
  const len = Math.max(parsed.length, live.length)
  return Array.from({ length: len }, (_, i) => {
    const p = parsed[i]
    const l = live[i]
    if (!p) return l
    if (!l) return p
    if (p.type === '思考' || l.type === '思考') {
      if (stepBodyLength(l) > stepBodyLength(p)) {
        return { ...l, index: p.index }
      }
      return p
    }
    if (!stepBodyLength(p) && stepBodyLength(l)) {
      return { ...l, index: p.index }
    }
    if ((l.displayBlock || '').length > (p.displayBlock || '').length) {
      return { ...p, ...l, index: p.index, displayBlock: l.displayBlock }
    }
    return p
  })
}

function isPdbStep(step: ProcessStep): boolean {
  const blob = `${step.title} ${step.name} ${step.inputSummary} ${step.resultSummary}`.toLowerCase()
  return blob.includes('pdb') || step.name.includes('蛋白质获取')
}

function ExpandedFields({ step }: { step: ProcessStep }) {
  const title = step.title?.trim() || ''
  const name = step.name?.trim() || ''
  const showTitle = Boolean(title)
  const showName = Boolean(name) && name !== title
  const input = formatToolOutputForDisplay(step.inputSummary || '')
  const result = formatToolOutputForDisplay(step.resultSummary || '')
  const detail = formatToolOutputForDisplay(step.detail || '')

  if (step.type === '思考') {
    const content = thinkingFullText({
      detail: step.detail,
      result: step.resultSummary,
      input: step.inputSummary,
      title: step.title,
    })
    return (
      <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
        {content && (
          <div className="whitespace-pre-wrap rounded bg-white/80 px-2 py-1.5 text-slate-700">{content}</div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
      {showTitle && (
        <div>
          <span className="font-medium text-slate-500">步骤：</span>
          {title}
        </div>
      )}
      {showName && (
        <div>
          <span className="font-medium text-slate-500">名称：</span>
          {name}
        </div>
      )}
      {input && (
        <div>
          <div className="mb-0.5 font-medium text-slate-500">参数</div>
          <div className="whitespace-pre-wrap rounded bg-white/80 px-2 py-1.5 text-slate-700">{input}</div>
        </div>
      )}
      {(result || detail) && (
        <div>
          <div className="mb-0.5 font-medium text-slate-500">输出</div>
          <div className="whitespace-pre-wrap rounded bg-white/80 px-2 py-1.5 text-slate-700">
            {(() => {
              const body = detail || result
              if (isJsonLikeToolOutput(body)) {
                return result && !isJsonLikeToolOutput(result) ? result : '（已完成，详见上方摘要）'
              }
              return body.length > 280 ? `${body.slice(0, 277)}…` : body
            })()}
          </div>
        </div>
      )}
      {isPdbStep(step) && (
        <PdbCardsFromStepText title={title} name={name} input={input} result={result} detail={detail} />
      )}
      {!input && !result && !detail && (
        <div className="text-slate-400">暂无详情（工具可能仍在执行或未返回结果）</div>
      )}
    </div>
  )
}

export default function ProcessPanel({ parsed, liveSteps }: Props) {
  const [open, setOpen] = useState(true)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  const steps = useMemo(() => {
    const fromLive =
      liveSteps && liveSteps.length > 0
        ? liveToProcessSteps(sortStepsForDisplay(liveSteps))
        : []
    if (parsed.hasProcess && parsed.steps.length > 0) {
      const fromParsed = parsed.steps.map((s) => ({
        ...s,
        inputSummary: stripProcessPaths(s.inputSummary),
        resultSummary: stripProcessPaths(s.resultSummary),
        detail: stripProcessPaths(s.detail),
      }))
      if (fromLive.length > 0) {
        return mergeDisplaySteps(fromParsed, fromLive)
      }
      return fromParsed
    }
    if (liveSteps && liveSteps.length > 0) return fromLive
    return []
  }, [liveSteps, parsed])

  const stepCounts = useMemo(() => countProcessPanelSteps(steps), [steps])
  const header = useMemo(() => buildProcessPanelHeader(stepCounts), [stepCounts])
  const displayAnswer = resolveDisplayAnswer(parsed, steps)
  const pdbIds = useMemo(() => collectPdbIdsFromProcessSteps(steps), [steps])
  const hasProcess = steps.length > 0 || parsed.hasProcess

  if (!hasProcess) {
    const plain = resolveDisplayAnswer(parsed, [])
    return (
      <div className="assistant-prose">
        <AssistantMarkdown>{plain || parsed.raw}</AssistantMarkdown>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className={getProcessPanelCardClassName()}>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          <span>{header}</span>
          <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        </button>

        {open && (
          <div className={getFinalStepListClassName()}>
            {steps.map((step, idx) => {
              const isExpanded = expanded[step.index] ?? false
              const stepKey = `${idx}-${step.index}-${step.title}-${step.name}`
              const isAction = step.type === '工具' || step.type === '技能'
              const thinkingFull = thinkingFullText({
                detail: step.detail,
                result: step.resultSummary,
                input: step.inputSummary,
                title: step.title,
              })
              const line = isAction
                ? `${formatStepStatusLine({
                    kind: step.type === '技能' ? 'skill' : 'tool',
                    name: step.name,
                    title: step.title,
                    status:
                      step.status === '进行中'
                        ? 'running'
                        : step.status === '失败'
                          ? 'failed'
                          : 'done',
                  })}${
                    step.inputSummary && !step.inputSummary.includes('mcporter')
                      ? ` · ${step.inputSummary}`
                      : ''
                  }${
                    step.resultSummary &&
                    !/^[\s{[]/.test(step.resultSummary) &&
                    !step.resultSummary.includes('"success"')
                      ? ` → ${step.resultSummary.slice(0, 100)}`
                      : ''
                  }`
                : thinkingSummaryLine(thinkingFull)
              const thinkingSummary = isAction ? '' : thinkingSummaryLine(thinkingFull)
              const hasThinkingDetail =
                !isAction &&
                thinkingFull.replace(/\s+/g, ' ').trim().length >
                  thinkingSummary.replace(/…$/, '').trim().length + 8
              const canExpand = isAction || hasThinkingDetail

              return (
                <div key={stepKey} className="rounded-lg border border-slate-100 bg-slate-50/80">
                  <button
                    type="button"
                    onClick={() => {
                      if (!canExpand) return
                      setExpanded((prev) => ({ ...prev, [step.index]: !prev[step.index] }))
                    }}
                    className={`flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm text-slate-700 ${
                      canExpand ? 'hover:bg-white' : ''
                    }`}
                  >
                    <StepBadge type={step.type} name={step.name} title={step.title} />
                    <span className="min-w-0 flex-1 leading-snug whitespace-pre-wrap">{line}</span>
                    {canExpand && (
                      <span className="shrink-0 text-xs text-slate-400">{isExpanded ? '▾' : '▸'}</span>
                    )}
                  </button>
                  {isExpanded && canExpand && <ExpandedFields step={step} />}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {pdbIds.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-slate-800">检索到的蛋白结构</h4>
          <PdbStructureCards pdbIds={pdbIds} />
        </div>
      )}

      {displayAnswer && (
        <div className="assistant-prose">
          <AssistantMarkdown>{displayAnswer}</AssistantMarkdown>
        </div>
      )}
    </div>
  )
}
