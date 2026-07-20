import { useCallback, useState } from 'react'
import { api } from '../api/client'
import type { Message, SelectedSkillHint, Session } from '../api/client'

export function useChat(initialSessionId?: string) {
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadSession = useCallback(async (id: string) => {
    const session = await api.getSession(id)
    setSessionId(session.id)
    setMessages(session.messages ?? [])
    setError(null)
  }, [])

  const sendMessage = useCallback(
    async (text: string, selectedSkill?: SelectedSkillHint) => {
      if (!text.trim() || loading) return
      setLoading(true)
      setError(null)

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])

      try {
        const res = await api.chat(text.trim(), sessionId, selectedSkill)
        if (!sessionId) setSessionId(res.session_id)
        const assistantMsg: Message = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: res.reply,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, assistantMsg])
        return res.session_id
      } catch (e) {
        setError(e instanceof Error ? e.message : '发送失败')
        setMessages((prev) => prev.slice(0, -1))
        return undefined
      } finally {
        setLoading(false)
      }
    },
    [sessionId, loading],
  )

  const newChat = useCallback(() => {
    setSessionId(undefined)
    setMessages([])
    setError(null)
  }, [])

  const isConversation = messages.length > 0

  return { sessionId, messages, loading, error, isConversation, loadSession, sendMessage, newChat }
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([])

  const refresh = useCallback(async () => {
    const list = await api.sessions()
    setSessions(list)
  }, [])

  const remove = useCallback(async (id: string) => {
    await api.deleteSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }, [])

  return { sessions, refresh, remove }
}
