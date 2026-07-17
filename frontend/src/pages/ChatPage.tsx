import { useEffect, useState, useImperativeHandle, forwardRef } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, type Skill } from '../api/client'
import { useChat } from '../hooks/useChat'
import WelcomeHeader from '../components/WelcomeHeader'
import SkillPlaza from '../components/SkillPlaza'
import MessageList from '../components/MessageList'
import ChatInput from '../components/ChatInput'

type LocationState = { prompt?: string }

export interface ChatPageHandle {
  newChat: () => void
  loadSession: (id: string) => void
  setPrompt: (text: string) => void
}

interface Props {
  onSessionChange?: (sessionId?: string) => void
}

const ChatPage = forwardRef<ChatPageHandle, Props>(function ChatPage({ onSessionChange }, ref) {
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { messages, loading, error, isConversation, loadSession, sendMessage, newChat } = useChat()
  const [input, setInput] = useState('')
  const [skills, setSkills] = useState<Skill[]>([])
  const [restoring, setRestoring] = useState(Boolean(routeSessionId))

  useEffect(() => {
    api.skills().then(setSkills).catch(console.error)
  }, [])

  // 从技能广场跳转时携带 prompt，填入对话框后清掉 state，避免刷新重复填充
  useEffect(() => {
    const prompt = (location.state as LocationState | null)?.prompt
    if (!prompt) return
    setInput(prompt)
    navigate(location.pathname, { replace: true, state: {} })
  }, [location.state, location.pathname, navigate])

  // 刷新 / 直链：从 URL 恢复会话（对齐 Matwings /chat/agent/:id）
  useEffect(() => {
    if (!routeSessionId) {
      setRestoring(false)
      return
    }
    let cancelled = false
    setRestoring(true)
    ;(async () => {
      try {
        await loadSession(routeSessionId)
        if (!cancelled) onSessionChange?.(routeSessionId)
      } catch (e) {
        console.error(e)
        if (!cancelled) {
          onSessionChange?.(undefined)
          navigate('/', { replace: true })
        }
      } finally {
        if (!cancelled) setRestoring(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when URL session changes
  }, [routeSessionId])

  useImperativeHandle(ref, () => ({
    newChat: () => {
      newChat()
      setInput('')
      setRestoring(false)
      navigate('/')
      onSessionChange?.(undefined)
    },
    loadSession: (id: string) => {
      navigate(`/c/${id}`)
    },
    setPrompt: (text: string) => setInput(text),
  }))

  const handleSend = async () => {
    const sid = await sendMessage(input)
    setInput('')
    if (sid) {
      onSessionChange?.(sid)
      if (!routeSessionId) navigate(`/c/${sid}`, { replace: true })
    }
  }

  if (restoring) {
    return (
      <div className="flex h-full flex-1 items-center justify-center text-sm text-slate-400">
        加载对话中…
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {!isConversation ? (
        <div className="flex-1 overflow-y-auto">
          <main className="mx-auto flex w-full max-w-7xl flex-col items-center px-3 pt-4 pb-16 md:px-8 md:pt-40 md:pb-20">
            <WelcomeHeader />
            <div className="h-px w-full" />
            <div className="w-full">
              <ChatInput
                variant="center"
                value={input}
                onChange={setInput}
                onSend={handleSend}
                loading={loading}
              />
            </div>

            {error && (
              <div className="w-full max-w-5xl px-1 py-2 text-center text-sm text-red-600">{error}</div>
            )}

            <div className="mt-2 w-full">
              <SkillPlaza
                skills={skills.slice(0, 30)}
                onSelect={(s) => setInput(s.example)}
                compact
                showTitle={false}
              />
            </div>
          </main>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-none bg-white p-0 md:m-2 md:rounded-[24px]">
          <MessageList messages={messages} loading={loading} />
          {error && <div className="px-4 py-2 text-center text-sm text-red-600">{error}</div>}
          <ChatInput value={input} onChange={setInput} onSend={handleSend} loading={loading} variant="footer" />
        </div>
      )}
    </div>
  )
})

export default ChatPage
