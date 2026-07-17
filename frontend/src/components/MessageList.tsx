import { useRef, useEffect } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Message } from '../api/client'

interface Props {
  messages: Message[]
  loading: boolean
}

const COL =
  'mx-auto w-full min-w-0 max-w-2xl lg:max-w-3xl xl:max-w-4xl 2xl:max-w-5xl'

export default function MessageList({ messages, loading }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

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
                  <div className="text-lg font-semibold text-[#4BA4F8]">猛犸智能体</div>
                </div>
                <div className="w-full overflow-hidden rounded-2xl border border-slate-200/70 bg-slate-50/70 px-4 py-3 md:px-5 md:py-4">
                  <div className="assistant-prose">
                    <Markdown remarkPlugins={[remarkGfm]}>{msg.content}</Markdown>
                  </div>
                </div>
              </div>
            ),
          )}

          {loading && (
            <div className="w-full min-w-0">
              <div className="flex items-center gap-2 pb-2">
                <div className="text-lg font-semibold text-[#4BA4F8]">猛犸智能体</div>
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
