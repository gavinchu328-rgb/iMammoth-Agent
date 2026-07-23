import { useMemo, useState } from 'react'
import type { LiveProcessStep } from '../api/client'
import type { ParsedAssistantReply, ProcessStep } from '../utils/parseProcessLog'
import { collectPdbIdsFromProcessSteps, resolveDisplayAnswer } from '../utils/parseProcessLog'
import { sortStepsForDisplay } from '../utils/sortSteps'
import {
  formatStepStatusLine,
  stepBadgeClass,
  stepBadgeLabel,
  stripProcessPaths,
} from '../utils/processStepUtils'
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
  }))
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
  const input = step.inputSummary || ''
  const result = step.resultSummary || ''
  const detail = step.detail || ''

  if (step.type === '思考') {
    const content = detail || result || input
    return (
      <div className="space-y-1 border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
        {content && (
          <div className="whitespace-pre-wrap">
            <span className="font-medium text-slate-500">内容：</span>
            {content}
          </div>
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
              if (/^[\s{[]/.test(body) || body.includes('"success"')) {
                return result && !/^[\s{[]/.test(result) ? result : '（已完成，详见上方摘要）'
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
      const parsedHasResults = fromParsed.some((s) => s.resultSummary || s.detail)
      const liveHasResults = fromLive.some((s) => s.resultSummary || s.detail)
      if (!parsedHasResults && liveHasResults) return fromLive
      return fromParsed
    }
    if (liveSteps && liveSteps.length > 0) return fromLive
    return []
  }, [liveSteps, parsed])

  const actionCount = useMemo(
    () => steps.filter((s) => s.type === '工具' || s.type === '技能').length,
    [steps],
  )
  const skillCount = useMemo(() => steps.filter((s) => s.type === '技能').length, [steps])
  const thinkCount = steps.length - actionCount
  const hasProcess = steps.length > 0 || parsed.hasProcess
  const displayAnswer = resolveDisplayAnswer(parsed, steps)
  const pdbIds = useMemo(() => collectPdbIdsFromProcessSteps(steps), [steps])

  if (!hasProcess) {
    const plain = resolveDisplayAnswer(parsed, [])
    return (
      <div className="assistant-prose">
        <AssistantMarkdown>{plain || parsed.raw}</AssistantMarkdown>
      </div>
    )
  }

  const header =
    skillCount > 0
      ? `分析过程 · ${steps.length} 步（思考 ${thinkCount} · 技能 ${skillCount} · 工具 ${actionCount - skillCount}）`
      : thinkCount > 0
        ? `分析过程 · ${steps.length} 步（思考 ${thinkCount} · 工具 ${actionCount}）`
        : `分析过程 · ${actionCount} 个工具`

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white/80">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          <span>{header}</span>
          <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        </button>

        {open && (
          <div className="space-y-2 border-t border-slate-100 px-3 py-3">
            {steps.map((step) => {
              const isExpanded = expanded[step.index] ?? false
              const isAction = step.type === '工具' || step.type === '技能'
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
                : (step.detail || step.resultSummary || step.inputSummary || step.title).slice(0, 300) +
                  ((step.detail || step.resultSummary || '').length > 300 ? '…' : '')

              return (
                <div key={step.index} className="rounded-lg border border-slate-100 bg-slate-50/80">
                  <button
                    type="button"
                    onClick={() =>
                      setExpanded((prev) => ({ ...prev, [step.index]: !prev[step.index] }))
                    }
                    className="flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-white"
                  >
                    <StepBadge type={step.type} name={step.name} title={step.title} />
                    <span className="min-w-0 flex-1 leading-snug whitespace-pre-wrap">{line}</span>
                    <span className="shrink-0 text-xs text-slate-400">{isExpanded ? '▾' : '▸'}</span>
                  </button>
                  {isExpanded && <ExpandedFields step={step} />}
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
