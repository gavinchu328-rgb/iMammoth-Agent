import { useCallback, useRef, useState } from 'react'
import { api } from '../api/client'
import type { LiveProcessStep, Message, SelectedSkillHint, Session } from '../api/client'

export type StreamingState = {
  content: string
  steps: LiveProcessStep[]
}

function mergeStep(steps: LiveProcessStep[], step: LiveProcessStep): LiveProcessStep[] {
  const next = [...steps]
  // 工具结果回填：按 tool_call_id 合并，保留原 title/name/input
  if (step.is_result_update && step.tool_call_id) {
    const idx = next.findIndex((s) => s.tool_call_id === step.tool_call_id)
    if (idx >= 0) {
      next[idx] = {
        ...next[idx],
        status: step.status || 'done',
        result: step.result || next[idx].result,
        detail: step.detail || next[idx].detail,
      }
      return next
    }
  }
  if (step.tool_call_id) {
    const idx = next.findIndex((s) => s.tool_call_id === step.tool_call_id)
    if (idx >= 0) {
      next[idx] = { ...next[idx], ...step }
      return next
    }
  }
  if (step.record_id) {
    const idx = next.findIndex((s) => s.record_id === step.record_id && s.kind === step.kind)
    if (idx >= 0) {
      next[idx] = { ...next[idx], ...step }
      return next
    }
  }
  next.push(step)
  return next
}

export function useChat(initialSessionId?: string) {
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState<StreamingState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const liveStepsRef = useRef<LiveProcessStep[]>([])

  const loadSession = useCallback(async (id: string) => {
    const session = await api.getSession(id)
    setSessionId(session.id)
    setMessages(session.messages ?? [])
    setStreaming(null)
    setError(null)
  }, [])

  const sendMessage = useCallback(
    async (text: string, selectedSkill?: SelectedSkillHint) => {
      if (!text.trim() || loading) return
      setLoading(true)
      setError(null)
      liveStepsRef.current = []
      setStreaming({ content: '', steps: [] })

      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: text.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      let resolvedSessionId = sessionId
      let streamFailed = false

      try {
        await api.chatStream(
          text.trim(),
          sessionId,
          selectedSkill,
          {
            onSession: (sid) => {
              resolvedSessionId = sid
              if (!sessionId) setSessionId(sid)
            },
            onDelta: (chunk) => {
              setStreaming((prev) =>
                prev ? { ...prev, content: prev.content + chunk } : { content: chunk, steps: [] },
              )
            },
            onStep: (step) => {
              liveStepsRef.current = mergeStep(liveStepsRef.current, step)
              const steps = liveStepsRef.current
              setStreaming((prev) =>
                prev ? { ...prev, steps } : { content: '', steps },
              )
            },
            onError: (message) => {
              streamFailed = true
              setError(message)
            },
            onDone: ({ session_id, reply, error: doneError, steps }) => {
              resolvedSessionId = session_id
              if (doneError) {
                streamFailed = true
                setError(doneError)
                return
              }
              const processSteps =
                (steps && steps.length > 0 ? steps : liveStepsRef.current) ?? []
              const assistantMsg: Message = {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: reply,
                created_at: new Date().toISOString(),
                process_steps: processSteps,
              }
              setMessages((prev) => [...prev, assistantMsg])
            },
          },
          controller.signal,
        )
      } catch (e) {
        if ((e as Error).name !== 'AbortError') {
          streamFailed = true
          setError(e instanceof Error ? e.message : '发送失败')
        } else {
          streamFailed = true
        }
      } finally {
        setStreaming(null)
        setLoading(false)
      }

      if (streamFailed) {
        setMessages((prev) => prev.slice(0, -1))
        return undefined
      }
      return resolvedSessionId
    },
    [sessionId, loading],
  )

  const newChat = useCallback(() => {
    abortRef.current?.abort()
    setSessionId(undefined)
    setMessages([])
    setStreaming(null)
    setError(null)
  }, [])

  const isConversation = messages.length > 0

  return {
    sessionId,
    messages,
    loading,
    streaming,
    error,
    isConversation,
    loadSession,
    sendMessage,
    newChat,
  }
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
