import { useRef, useEffect, useMemo } from 'react'
import type { Message } from '../api/client'
import type { StreamingState } from '../hooks/useChat'
import LiveProcessPanel from './LiveProcessPanel'
import ProcessPanel from './ProcessPanel'
import { parseProcessLog } from '../utils/parseProcessLog'

interface Props {
  messages: Message[]
  loading: boolean
  streaming?: StreamingState | null
}

const COL =
  'mx-auto w-full min-w-0 max-w-2xl lg:max-w-3xl xl:max-w-4xl 2xl:max-w-5xl'

function AssistantContent({ content, liveSteps }: { content: string; liveSteps?: Message['process_steps'] }) {
  const parsed = useMemo(() => parseProcessLog(content), [content])
  return <ProcessPanel parsed={parsed} liveSteps={liveSteps} />
}

export default function MessageList({ messages, loading, streaming }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading, streaming?.content, streaming?.steps.length])

  const streamingParsed = useMemo(
    () => (streaming?.content ? parseProcessLog(streaming.content) : null),
    [streaming?.content],
  )

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <div className="flex min-h-full min-w-0 flex-col items-center px-2 py-6 md:px-4 md:pb-10">
        <div className={`${COL} space-y-6`}>
          {messages.map((msg) =>
            msg.role === 'user' ? (
              <div key={msg.id} className="flex justify-end">
                <div className="max-w-[85%] rounded-lg bg-black/[0.06] px-4 py-3 text-[15px] leading-[1.7] text-black/88">
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ) : (
              <div key={msg.id} className="w-full min-w-0">
                <div className="flex items-center gap-2 pb-2">
                  <div className="text-lg font-semibold text-[#4BA4F8]">iMammoth Agent</div>
                </div>
                <div className="w-full overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50/70 px-4 py-3 md:px-5 md:py-4">
                  <AssistantContent content={msg.content} liveSteps={msg.process_steps} />
                </div>
              </div>
            ),
          )}

          {loading && streaming && (
            <div className="w-full min-w-0">
              <div className="flex items-center gap-2 pb-2">
                <div className="text-lg font-semibold text-[#4BA4F8]">iMammoth Agent</div>
              </div>
              <div className="w-full overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50/70 px-4 py-3 md:px-5 md:py-4">
                {streaming.steps.length > 0 || streaming.content ? (
                  <LiveProcessPanel
                    steps={streaming.steps}
                    content={
                      streamingParsed?.hasProcess
                        ? streamingParsed.finalAnswer || undefined
                        : streaming.content || undefined
                    }
                  />
                ) : (
                  <div className="flex items-center gap-2 text-sm text-slate-500">
                    <div className="flex gap-1">
                      <span className="h-2 w-2 animate-bounce rounded-full bg-[#4BA4F8]" style={{ animationDelay: '0ms' }} />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-[#4BA4F8]" style={{ animationDelay: '150ms' }} />
                      <span className="h-2 w-2 animate-bounce rounded-full bg-[#4BA4F8]" style={{ animationDelay: '300ms' }} />
                    </div>
                    思考中...
                  </div>
                )}
              </div>
            </div>
          )}

          {loading && !streaming && (
            <div className="w-full min-w-0">
              <div className="flex items-center gap-2 pb-2">
                <div className="text-lg font-semibold text-[#4BA4F8]">iMammoth Agent</div>
              </div>
              <div className="flex items-center gap-2 rounded-2xl border border-slate-200/70 bg-slate-50/70 px-4 py-3 text-sm text-slate-500">
                <div className="flex gap-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[#4BA4F8]" style={{ animationDelay: '0ms' }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[#4BA4F8]" style={{ animationDelay: '150ms' }} />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-[#4BA4F8]" style={{ animationDelay: '300ms' }} />
                </div>
                思考中...
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      </div>
    </div>
  )
}
