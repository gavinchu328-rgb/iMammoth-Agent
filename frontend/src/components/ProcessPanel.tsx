import { useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ParsedAssistantReply } from '../utils/parseProcessLog'

interface Props {
  parsed: ParsedAssistantReply
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

export default function ProcessPanel({ parsed }: Props) {
  const [open, setOpen] = useState(true)
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})

  if (!parsed.hasProcess) {
    return (
      <div className="assistant-prose">
        <Markdown remarkPlugins={[remarkGfm]}>{parsed.finalAnswer || parsed.raw}</Markdown>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white/80">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800 hover:bg-slate-50"
        >
          <span>分析过程 · {parsed.toolCount} 个工具</span>
          <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        </button>

        {open && (
          <div className="space-y-2 border-t border-slate-100 px-3 py-3">
            {parsed.steps.map((step) => {
              const isExpanded = expanded[step.index] ?? false
              const line =
                step.type === '工具'
                  ? `${step.status || '已执行'} ${step.name}${step.inputSummary ? ` · ${step.inputSummary}` : ''}`
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
                    <span className="min-w-0 flex-1 leading-snug">{line}</span>
                    <span className="shrink-0 text-xs text-slate-400">{isExpanded ? '▾' : '▸'}</span>
                  </button>
                  {isExpanded && (
                    <div className="space-y-1 border-t border-slate-100 px-3 py-2 text-xs text-slate-600">
                      <div>
                        <span className="font-medium text-slate-500">步骤：</span>
                        {step.title}
                      </div>
                      {step.name && (
                        <div>
                          <span className="font-medium text-slate-500">名称：</span>
                          {step.name}
                        </div>
                      )}
                      {step.inputSummary && (
                        <div>
                          <span className="font-medium text-slate-500">输入：</span>
                          {step.inputSummary}
                        </div>
                      )}
                      {step.resultSummary && (
                        <div>
                          <span className="font-medium text-slate-500">结果：</span>
                          {step.resultSummary}
                        </div>
                      )}
                      {step.detail && (
                        <div>
                          <span className="font-medium text-slate-500">详情：</span>
                          {step.detail}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {parsed.finalAnswer && (
        <div className="assistant-prose">
          <Markdown remarkPlugins={[remarkGfm]}>{parsed.finalAnswer}</Markdown>
        </div>
      )}
    </div>
  )
}
