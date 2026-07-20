import type { LiveProcessStep } from '../api/client'

interface Props {
  steps: LiveProcessStep[]
  content?: string
}

function StepBadge({ kind }: { kind: LiveProcessStep['kind'] }) {
  const isTool = kind === 'tool'
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

export default function LiveProcessPanel({ steps, content }: Props) {
  const toolCount = steps.filter((s) => s.kind === 'tool').length
  const thinkCount = steps.length - toolCount
  const header =
    thinkCount > 0
      ? `分析过程 · ${steps.length} 步（思考 ${thinkCount} · 工具 ${toolCount}）`
      : `分析过程 · ${toolCount} 个工具`

  return (
    <div className="space-y-4">
      {steps.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-slate-200/80 bg-white/80">
          <div className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800">
            <span>{header}</span>
            <span className="text-xs font-normal text-emerald-600">实时更新中</span>
          </div>
          <div className="space-y-2 border-t border-slate-100 px-3 py-3">
            {steps.map((step, i) => {
              const input = stripPaths(step.input || '')
              const line =
                step.kind === 'tool'
                  ? `${step.status === 'running' ? '执行中' : '已执行'} ${step.name}${
                      input ? ` · ${input}` : ''
                    }`
                  : stripPaths(step.result || step.input || step.title)

              return (
                <div
                  key={step.tool_call_id || step.record_id || `${step.kind}-${i}`}
                  className="rounded-lg border border-slate-100 bg-slate-50/80 px-3 py-2.5"
                >
                  <div className="flex items-start gap-2 text-sm text-slate-700">
                    <StepBadge kind={step.kind} />
                    <span className="min-w-0 flex-1 leading-snug whitespace-pre-wrap">{line}</span>
                    {step.status === 'running' && (
                      <span className="shrink-0 text-xs text-blue-500">进行中</span>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {content && (
        <div className="assistant-prose whitespace-pre-wrap text-[15px] leading-relaxed text-slate-800">
          {content}
        </div>
      )}
    </div>
  )
}
