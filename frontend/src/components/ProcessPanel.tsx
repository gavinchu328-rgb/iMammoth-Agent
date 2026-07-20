import { useMemo, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { LiveProcessStep } from '../api/client'
import type { ParsedAssistantReply, ProcessStep } from '../utils/parseProcessLog'

interface Props {
  parsed: ParsedAssistantReply
  liveSteps?: LiveProcessStep[]
}

function StepBadge({ type }: { type: string }) {
  const isTool = type === '工具'
  return (
    <span
      className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
        isTool ? 'bg-blue-100 text-blue-700' : 'bg-violet-100 text-violet-700'
      }`}
    >
      {isTool ? 'MCP' : '思考'}
    </span>
  )
}

/** 隐藏绝对路径，只保留文件名 / 技能名 */
function stripPaths(text: string): string {
  return text
    .replace(/(?:~|\/home\/|\/data\d?\/|\/tmp\/|\.\/)[^\s"']+/g, (p) => {
      const skill = p.match(/(?:skills|skill)[/\\]([^/\\]+)[/\\]SKILL\.md/i)
      if (skill) return `技能「${skill[1]}」`
      const base = p.replace(/\/+$/, '').split('/').pop()
      return base || '文件'
    })
    .trim()
}

function liveToProcessSteps(live: LiveProcessStep[]): ProcessStep[] {
  return live.map((step, i) => ({
    index: i + 1,
    title: step.title || step.name || (step.kind === 'tool' ? '工具' : '深度思考'),
    type: step.kind === 'tool' ? '工具' : '思考',
    status: step.status === 'running' ? '进行中' : step.status === 'failed' ? '失败' : '已执行',
    name: step.name || '',
    inputSummary: stripPaths(step.input || ''),
    resultSummary: stripPaths(step.result || ''),
    detail: stripPaths(step.detail || ''),
  }))
}

function ExpandedFields({ step }: { step: ProcessStep }) {
  const title = step.title?.trim() || ''
  const name = step.name?.trim() || ''
  const showTitle = Boolean(title)
  const showName = Boolean(name) && name !== title
  const input = stripPaths(step.inputSummary || '')
  const result = stripPaths(step.resultSummary || '')
  const detail = stripPaths(step.detail || '')

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
            {detail || result}
          </div>
        </div>
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
    // 优先用解析后的规范步骤（标题更友好）；无则退回实时步骤
    if (parsed.hasProcess && parsed.steps.length > 0) {
      return parsed.steps.map((s) => ({
        ...s,
        inputSummary: stripPaths(s.inputSummary),
        resultSummary: stripPaths(s.resultSummary),
        detail: stripPaths(s.detail),
      }))
    }
    if (liveSteps && liveSteps.length > 0) return liveToProcessSteps(liveSteps)
    return []
  }, [liveSteps, parsed])

  const toolCount = useMemo(
    () => steps.filter((s) => s.type === '工具').length,
    [steps],
  )
  const thinkCount = steps.length - toolCount
  const hasProcess = steps.length > 0 || parsed.hasProcess
  const finalAnswer = parsed.finalAnswer || (!parsed.hasProcess ? parsed.raw : '')

  if (!hasProcess) {
    return (
      <div className="assistant-prose">
        <Markdown remarkPlugins={[remarkGfm]}>{finalAnswer || parsed.raw}</Markdown>
      </div>
    )
  }

  const header =
    thinkCount > 0
      ? `分析过程 · ${steps.length} 步（思考 ${thinkCount} · 工具 ${toolCount}）`
      : `分析过程 · ${toolCount} 个工具`

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
              const line =
                step.type === '工具'
                  ? `${step.status || '已执行'} ${step.name || step.title}${
                      step.inputSummary ? ` · ${step.inputSummary}` : ''
                    }`
                  : step.resultSummary || step.inputSummary || step.title

              return (
                <div key={step.index} className="rounded-lg border border-slate-100 bg-slate-50/80">
                  <button
                    type="button"
                    onClick={() =>
                      setExpanded((prev) => ({ ...prev, [step.index]: !prev[step.index] }))
                    }
                    className="flex w-full items-start gap-2 px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-white"
                  >
                    <StepBadge type={step.type} />
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

      {finalAnswer && (
        <div className="assistant-prose">
          <Markdown remarkPlugins={[remarkGfm]}>{finalAnswer}</Markdown>
        </div>
      )}
    </div>
  )
}
