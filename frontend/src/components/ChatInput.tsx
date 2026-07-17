import { useEffect, useRef } from 'react'

interface Props {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  loading: boolean
  placeholder?: string
  /** center = welcome 大输入框；footer = 对话态紧凑输入框 */
  variant?: 'footer' | 'center'
}

function SendButton({
  disabled,
  loading,
  onClick,
}: {
  disabled: boolean
  loading: boolean
  onClick: () => void
}) {
  const inactive = disabled || loading

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={inactive}
      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-colors ${
        inactive
          ? 'cursor-not-allowed bg-[#E5E6EB]'
          : 'cursor-pointer bg-[#3370FF] shadow-sm hover:bg-[#2860E1]'
      }`}
      aria-label="发送"
    >
      {loading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-[#A8ABB2]/40 border-t-[#A8ABB2]" />
      ) : (
        <svg
          viewBox="0 0 16 16"
          className={`h-4 w-4 ${inactive ? 'text-[#A8ABB2]' : 'text-white'}`}
          fill="currentColor"
          aria-hidden="true"
        >
          <path d="M8 2.2 13.8 8.6H10.2V13.8H5.8V8.6H2.2L8 2.2Z" />
        </svg>
      )}
    </button>
  )
}

const WIDTH =
  'mx-auto w-full min-w-[200px] max-w-2xl lg:max-w-3xl xl:max-w-4xl 2xl:max-w-5xl'

export default function ChatInput({
  value,
  onChange,
  onSend,
  loading,
  placeholder,
  variant = 'footer',
}: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const isCenter = variant === 'center'

  const defaultPlaceholder = '请输入您的科研问题或任务描述…'

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, isCenter ? 400 : 160) + 'px'
  }, [value, isCenter])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim() && !loading) onSend()
    }
  }

  // Welcome: 大输入框 border-[#808080] + md:min-h-[120px]
  // Conversation: compact rounded-[24px] border-slate-300，无大 min-height
  const boxClass = isCenter
    ? 'relative my-4 w-full rounded-2xl border border-[#808080] bg-white transition-all duration-300 md:rounded-[20px] focus-within:border-[#808080] focus-within:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.15)]'
    : 'relative w-full rounded-[24px] border border-slate-300 bg-white/80 shadow-[0_4px_24px_-4px_rgba(0,0,0,0.1)] backdrop-blur-2xl transition-all duration-300 focus-within:border-indigo-500 focus-within:shadow-[0_8px_30px_-4px_rgba(0,0,0,0.15)]'

  const padClass = isCenter ? 'px-3 pt-3 md:px-4 md:pt-4' : 'px-5 pt-3 md:px-6'
  const footPad = isCenter ? 'px-3 pb-2 md:px-4 md:pb-4' : 'px-5 pb-3 md:px-6'

  const textareaClass = isCenter
    ? 'max-h-[400px] min-h-[56px] w-full resize-none border-0 bg-transparent px-0 py-0 text-sm leading-relaxed text-slate-700 outline-none placeholder:text-slate-400 focus:ring-0 md:min-h-[120px] md:text-lg'
    : 'max-h-[160px] w-full resize-none border-0 bg-transparent px-0 py-0 text-base leading-relaxed text-slate-700 outline-none placeholder:text-slate-400 focus:ring-0'

  const inputBox = (
    <div className={boxClass}>
      <div className={padClass}>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? defaultPlaceholder}
          rows={isCenter ? 1 : 2}
          className={textareaClass}
        />
      </div>
      <div className={`flex items-center justify-end ${footPad}`}>
        <SendButton disabled={!value.trim() || loading} loading={loading} onClick={onSend} />
      </div>
    </div>
  )

  if (isCenter) {
    return (
      <div className="sticky top-0 z-30 -mt-2 w-full pt-2">
        <div className={`relative z-20 mb-6 ${WIDTH}`}>{inputBox}</div>
      </div>
    )
  }

  return (
    <div className="shrink-0 px-2 pb-4 pt-2 md:px-4 md:pb-6">
      <div className={WIDTH}>{inputBox}</div>
    </div>
  )
}
