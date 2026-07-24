import { useCallback, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ChatStreamSession, LiveProcessStep, Message, SelectedSkillHint, Session } from '../api/client'
import { useApiRetry } from './useApiRetry'
import { newId } from '../utils/id'
import { hasReplyReady } from '../utils/liveActivity'
import { isLowQualityFinalAnswer, parseProcessLog } from '../utils/parseProcessLog'
import {
  extractReplyFromSnapshot,
  RESUME_INCOMPLETE_ERROR,
  RESUME_PARTIAL_WARNING,
  shouldPreferProcessLogReply,
  shouldResumeInProgress,
} from '../utils/processLogResume'
import { mergeProcessStep } from '../utils/processSteps'
import { resolveSkillForTurn } from '../utils/skillRouting'
import { frontendTimeoutMs } from '../utils/streamBudget'

export type StreamingState = {
  content: string
  steps: LiveProcessStep[]
  skillName?: string
  skillCategory?: string
}

function buildStoppedReply(content: string): string {
  const trimmed = content.trim()
  if (!trimmed) return '（已停止生成）'
  const parsed = parseProcessLog(trimmed)
  let reply = parsed.hasProcess ? trimmed : parsed.finalAnswer || trimmed
  if (!hasReplyReady(reply) && !reply.includes('（已停止生成）')) {
    reply = `${reply.trim()}\n\n（已停止生成）`
  }
  return reply
}

function enrichMessagesWithProcessLog(messages: Message[], steps: LiveProcessStep[]): Message[] {
  if (!steps.length) return messages
  const lastAssistantIdx = messages.map((m, i) => (m.role === 'assistant' ? i : -1)).filter((i) => i >= 0).pop()
  if (lastAssistantIdx == null) return messages
  return messages.map((m, i) => {
    if (i !== lastAssistantIdx || m.role !== 'assistant') return m
    const existing = m.process_steps?.length ?? 0
    if (existing >= steps.length) return m
    return { ...m, process_steps: steps }
  })
}

export function useChat(initialSessionId?: string) {
  const [sessionId, setSessionId] = useState<string | undefined>(initialSessionId)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [streaming, setStreaming] = useState<StreamingState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const liveStepsRef = useRef<LiveProcessStep[]>([])
  const streamingContentRef = useRef('')
  const activeSessionIdRef = useRef<string | undefined>(undefined)
  const userStopRef = useRef(false)
  const requestEpochRef = useRef(0)
  const finalizedRef = useRef(false)

  const activeSkillRef = useRef<SelectedSkillHint | undefined>(undefined)
  const userTurnRef = useRef(0)

  const finalizeAssistantReply = useCallback(
    (reply: string, processSteps: LiveProcessStep[], ownsRequest: () => boolean) => {
      if (!ownsRequest() || finalizedRef.current) return
      finalizedRef.current = true
      const assistantMsg: Message = {
        id: newId(),
        role: 'assistant',
        content: reply,
        created_at: new Date().toISOString(),
        process_steps: processSteps,
      }
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last?.role === 'assistant') {
          return [...prev.slice(0, -1), { ...last, content: reply, process_steps: processSteps }]
        }
        return [...prev, assistantMsg]
      })
      liveStepsRef.current = []
      setStreaming(null)
      setLoading(false)
    },
    [],
  )

  const buildStreamHandlers = useCallback(
    (
      ownsRequest: () => boolean,
      resolvedRef: { current: string },
      onFailed?: () => void,
      onStreamBudget?: (budgetSec: number) => void,
    ) => ({
      onSession: (payload: ChatStreamSession) => {
        if (!ownsRequest()) return
        const sid = payload.session_id
        resolvedRef.current = sid
        activeSessionIdRef.current = sid
        if (!sessionId) setSessionId(sid)
        if (payload.stream_budget_sec != null) {
          onStreamBudget?.(payload.stream_budget_sec)
        }
      },
      onDelta: (chunk: string) => {
        if (!ownsRequest()) return
        setStreaming((prev) => {
          const next = prev
            ? { ...prev, content: prev.content + chunk }
            : { content: chunk, steps: [] }
          streamingContentRef.current = next.content
          return next
        })
      },
      onStep: (step: LiveProcessStep) => {
        if (!ownsRequest()) return
        liveStepsRef.current = mergeProcessStep(liveStepsRef.current, step)
        const steps = liveStepsRef.current
        setStreaming((prev) => (prev ? { ...prev, steps } : { content: '', steps }))
      },
      onSteps: (steps: LiveProcessStep[]) => {
        if (!ownsRequest()) return
        liveStepsRef.current = steps
        setStreaming((prev) => (prev ? { ...prev, steps } : { content: '', steps }))
      },
      onError: (message: string) => {
        if (!ownsRequest()) return
        onFailed?.()
        setError(message)
      },
      onDone: (payload: {
        session_id?: string
        reply?: string
        error?: string | null
        steps?: LiveProcessStep[]
      }) => {
        if (!ownsRequest()) return
        const session_id = payload.session_id || resolvedRef.current
        const reply = payload.reply || ''
        resolvedRef.current = session_id
        if (payload.error) {
          onFailed?.()
          // 「未收到完成标记」时由 sendMessage 末尾统一从过程日志恢复
          if (!String(payload.error).includes('未收到完成标记')) {
            setError(payload.error)
          }
          return
        }
        const processSteps =
          (payload.steps && payload.steps.length > 0 ? payload.steps : liveStepsRef.current) ?? []
        finalizeAssistantReply(reply, processSteps, ownsRequest)
      },
    }),
    [finalizeAssistantReply, sessionId],
  )

  const recoverIncompleteReply = useCallback(
    async (
      sid: string,
      ownsRequest: () => boolean,
      tailHandlers?: ReturnType<typeof buildStreamHandlers>,
      signal?: AbortSignal,
    ): Promise<boolean> => {
      if (!ownsRequest() || finalizedRef.current) return finalizedRef.current

      try {
        let snap = await api.getProcessLog(sid)
        if (!ownsRequest() || finalizedRef.current) return finalizedRef.current

        if (snap.in_progress && tailHandlers && signal) {
          await api.tailProcessLog(sid, tailHandlers, signal, snap.log_offset)
          snap = await api.getProcessLog(sid)
        }

        if (!ownsRequest() || finalizedRef.current) return finalizedRef.current

        if (snap.reply?.trim() && !isLowQualityFinalAnswer(snap.reply)) {
          finalizeAssistantReply(snap.reply, snap.steps ?? liveStepsRef.current, ownsRequest)
          return true
        }

        const session = await api.getSession(sid)
        const last = session.messages?.[session.messages.length - 1]
        if (last?.role === 'assistant' && last.content?.trim()) {
          finalizeAssistantReply(last.content, last.process_steps ?? liveStepsRef.current, ownsRequest)
          return true
        }
      } catch (e) {
        console.error('恢复对话结果失败', e)
      }
      return finalizedRef.current
    },
    [finalizeAssistantReply, buildStreamHandlers],
  )

  const resumeProcessLog = useCallback(
    async (
      id: string,
      requestEpoch: number,
      controller: AbortController,
      awaitingReply = false,
      onBudgetKnown?: (budgetSec: number) => void,
    ) => {
      const ownsRequest = () => requestEpoch === requestEpochRef.current
      const resolvedRef = { current: id }

      let snap
      try {
        snap = await api.getProcessLog(id)
      } catch {
        return
      }
      if (!ownsRequest()) return

      if (snap.stream_budget_sec != null) {
        onBudgetKnown?.(snap.stream_budget_sec)
      }

      const handlers = buildStreamHandlers(
        ownsRequest,
        resolvedRef,
        () => undefined,
        onBudgetKnown,
      )

      if (shouldResumeInProgress(snap, awaitingReply)) {
        const steps = snap.steps ?? []
        const content = snap.content || ''
        const quickReply = extractReplyFromSnapshot(snap, content)
        if (quickReply) {
          finalizeAssistantReply(quickReply, steps, ownsRequest)
          return
        }
        liveStepsRef.current = steps
        streamingContentRef.current = content
        activeSessionIdRef.current = id
        finalizedRef.current = false
        setLoading(true)
        setStreaming({ content, steps })
        try {
          await api.tailProcessLog(id, handlers, controller.signal, snap.log_offset)
        } catch (e) {
          if (ownsRequest() && (e as Error).name !== 'AbortError') {
            setError(e instanceof Error ? e.message : '恢复过程日志失败')
          }
        }
        if (ownsRequest() && !finalizedRef.current) {
          await recoverIncompleteReply(id, ownsRequest, handlers, controller.signal)
        }
        if (ownsRequest() && !finalizedRef.current) {
          const steps = liveStepsRef.current
          const content = streamingContentRef.current
          const hasPartial = steps.length > 0 || content.trim().length > 0
          setLoading(false)
          if (hasPartial) {
            setStreaming({ content, steps })
            setError(RESUME_PARTIAL_WARNING)
          } else {
            setStreaming(null)
            setError(RESUME_INCOMPLETE_ERROR)
          }
        }
        return
      }

      if (snap.done && snap.reply && awaitingReply) {
        finalizeAssistantReply(snap.reply, snap.steps ?? [], ownsRequest)
      }
    },
    [buildStreamHandlers, finalizeAssistantReply, recoverIncompleteReply],
  )

  const loadSession = useCallback(
    async (id: string) => {
      requestEpochRef.current += 1
      const requestEpoch = requestEpochRef.current
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      let timeoutId = window.setTimeout(
        () => controller.abort(),
        frontendTimeoutMs('', undefined, 7200),
      )
      const resetStreamTimeout = (budgetSec: number) => {
        window.clearTimeout(timeoutId)
        timeoutId = window.setTimeout(
          () => controller.abort(),
          frontendTimeoutMs('', undefined, budgetSec),
        )
      }

      const session = await api.getSession(id)
      if (requestEpoch !== requestEpochRef.current) return

      let msgs = session.messages ?? []
      try {
        const snap = await api.getProcessLog(id)
        if (requestEpoch !== requestEpochRef.current) return
        msgs = enrichMessagesWithProcessLog(msgs, snap.steps ?? [])
        const healedReply = snap.reply?.trim()
        if (healedReply && snap.done && !snap.in_progress) {
          const lastAssistantIdx = msgs
            .map((m, i) => (m.role === 'assistant' ? i : -1))
            .filter((i) => i >= 0)
            .pop()
          if (lastAssistantIdx != null) {
            const dbContent = msgs[lastAssistantIdx].content || ''
            if (shouldPreferProcessLogReply(dbContent, healedReply)) {
              msgs = msgs.map((m, i) =>
                i === lastAssistantIdx
                  ? {
                      ...m,
                      content: healedReply,
                      process_steps: snap.steps?.length ? snap.steps : m.process_steps,
                    }
                  : m,
              )
            }
          }
        }
      } catch {
        // 过程日志不可用时仍展示会话正文
      }

      const awaitingReply = msgs[msgs.length - 1]?.role === 'user'

      setSessionId(session.id)
      activeSessionIdRef.current = session.id
      setMessages(msgs)
      setStreaming(null)
      setError(null)
      setLoading(false)
      liveStepsRef.current = []
      finalizedRef.current = false

      // Resume tail stream in background — awaiting it here blocks ChatPage
      // "加载对话中…" until the SSE closes (can be minutes for in-flight runs).
      void resumeProcessLog(
        id,
        requestEpoch,
        controller,
        awaitingReply,
        resetStreamTimeout,
      ).finally(() => {
        window.clearTimeout(timeoutId)
      })
    },
    [resumeProcessLog],
  )

  const sendMessage = useCallback(
    async (text: string, selectedSkill?: SelectedSkillHint) => {
      if (!text.trim() || loading) return
      const requestEpoch = ++requestEpochRef.current
      const ownsRequest = () => requestEpoch === requestEpochRef.current

      const messageText = text.trim().replace(/^undefined+/i, '')
      if (!messageText) return

      const skillForTurn = resolveSkillForTurn(messageText, selectedSkill, activeSkillRef.current)
      if (skillForTurn) {
        activeSkillRef.current = skillForTurn
      } else {
        activeSkillRef.current = undefined
      }
      userTurnRef.current += 1

      setLoading(true)
      setError(null)
      liveStepsRef.current = []
      streamingContentRef.current = ''
      activeSessionIdRef.current = sessionId
      userStopRef.current = false
      finalizedRef.current = false
      setStreaming({
        content: '',
        steps: [],
        skillName: skillForTurn?.name,
        skillCategory: skillForTurn?.category,
      })

      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      let timeoutId = window.setTimeout(
        () => controller.abort(),
        frontendTimeoutMs(messageText, skillForTurn?.name),
      )
      const resetStreamTimeout = (budgetSec: number) => {
        window.clearTimeout(timeoutId)
        timeoutId = window.setTimeout(
          () => controller.abort(),
          frontendTimeoutMs(messageText, skillForTurn?.name, budgetSec),
        )
      }

      let resolvedSessionId = sessionId
      let streamFailed = false
      const resolvedRef = { current: sessionId || '' }

      const streamHandlers = buildStreamHandlers(
        ownsRequest,
        resolvedRef,
        () => {
          streamFailed = true
        },
        resetStreamTimeout,
      )

      try {
        const userMsg: Message = {
          id: newId(),
          role: 'user',
          content: messageText,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, userMsg])

        await api.chatStream(
          messageText,
          sessionId,
          skillForTurn,
          streamHandlers,
          controller.signal,
        )
        resolvedSessionId = resolvedRef.current || resolvedSessionId

        if (ownsRequest() && !finalizedRef.current && resolvedSessionId) {
          await recoverIncompleteReply(resolvedSessionId, ownsRequest, streamHandlers, controller.signal)
        }
      } catch (e) {
        if (!ownsRequest()) return undefined
        if ((e as Error).name === 'AbortError') {
          if (userStopRef.current && !finalizedRef.current) {
            const reply = buildStoppedReply(streamingContentRef.current)
            finalizeAssistantReply(reply, [...liveStepsRef.current], ownsRequest)
          }
          userStopRef.current = false
          return undefined
        }
        streamFailed = true
        setError(e instanceof Error ? e.message : '发送失败')
      }

      window.clearTimeout(timeoutId)
      if (!ownsRequest()) return undefined

      if (!finalizedRef.current) {
        const sid = resolvedRef.current || resolvedSessionId
        if (sid) {
          await recoverIncompleteReply(sid, ownsRequest, streamHandlers, controller.signal)
        }
      }

      if (!ownsRequest()) return undefined
      if (!finalizedRef.current) {
        if (liveStepsRef.current.length > 0 || streamingContentRef.current.trim()) {
          setError((prev) => prev ?? '连接中断，请刷新页面从历史记录查看结果')
        }
        setStreaming(null)
        setLoading(false)
      }

      if (!ownsRequest()) return undefined
      if (streamFailed && !userStopRef.current) {
        setMessages((prev) => {
          if (
            finalizedRef.current &&
            prev.length >= 2 &&
            prev[prev.length - 1]?.role === 'assistant'
          ) {
            return prev.slice(0, -2)
          }
          return prev.slice(0, -1)
        })
        finalizedRef.current = false
        return undefined
      }
      return resolvedSessionId
    },
    [sessionId, loading, buildStreamHandlers, recoverIncompleteReply],
  )

  const stopGeneration = useCallback(async () => {
    if (!loading) return

    const requestEpoch = requestEpochRef.current
    const ownsRequest = () => requestEpoch === requestEpochRef.current
    userStopRef.current = true

    const steps = [...liveStepsRef.current]
    const reply = buildStoppedReply(streamingContentRef.current)
    if (!finalizedRef.current) {
      finalizeAssistantReply(reply, steps, ownsRequest)
    }

    abortRef.current?.abort()

    const sid = activeSessionIdRef.current || sessionId
    if (sid) {
      try {
        const result = await api.stopSession(sid, reply)
        if (ownsRequest() && result.reply) {
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last?.role !== 'assistant') return prev
            if (last.content === result.reply) return prev
            return [...prev.slice(0, -1), { ...last, content: result.reply, process_steps: steps }]
          })
        }
      } catch (err) {
        console.error('停止会话失败', err)
      }
    }

    userStopRef.current = false
  }, [loading, sessionId, finalizeAssistantReply])

  const newChat = useCallback(() => {
    requestEpochRef.current += 1
    abortRef.current?.abort()
    abortRef.current = null
    liveStepsRef.current = []
    streamingContentRef.current = ''
    activeSessionIdRef.current = undefined
    userStopRef.current = false
    finalizedRef.current = false
    activeSkillRef.current = undefined
    userTurnRef.current = 0
    setSessionId(undefined)
    setMessages([])
    setStreaming(null)
    setError(null)
    setLoading(false)
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
    stopGeneration,
    newChat,
  }
}

export function useSessions() {
  const [sessions, setSessions] = useState<Session[]>([])

  const refresh = useCallback(async () => {
    const list = await api.sessions()
    setSessions(list)
    return list
  }, [])

  const loadStatus = useApiRetry(
    useCallback(async () => {
      await refresh()
    }, [refresh]),
  )

  const remove = useCallback(async (id: string) => {
    await api.deleteSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
  }, [])

  return { sessions, refresh, remove, loadStatus }
}
