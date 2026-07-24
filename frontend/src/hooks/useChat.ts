import { useCallback, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ChatStreamSession, LiveProcessStep, Message, SelectedSkillHint, Session } from '../api/client'
import { useApiRetry } from './useApiRetry'
import { newId } from '../utils/id'
import { hasReplyReady, isAnalysisComplete } from '../utils/liveActivity'
import { parseProcessLog, resolveDisplayAnswer, type SummaryStep } from '../utils/parseProcessLog'
import {
  extractReplyFromSnapshot,
  RESUME_INCOMPLETE_ERROR,
  shouldResumeInProgress,
} from '../utils/processLogResume'
import { mergeProcessStep } from '../utils/processSteps'
import { frontendTimeoutMs } from '../utils/streamBudget'

export type StreamingState = {
  content: string
  steps: LiveProcessStep[]
  skillName?: string
  skillCategory?: string
}

function liveStepsToSummarySteps(steps: LiveProcessStep[]): SummaryStep[] {
  return steps.map((step) => ({
    type: step.kind === 'skill' ? '技能' : step.kind === 'thinking' ? '思考' : '工具',
    title: step.title || step.name || '工具',
    name: step.name || '',
    resultSummary: step.result || '',
    detail: step.detail || '',
    displayBlock: step.display_block,
  }))
}

function buildEarlyFinalizeReply(content: string, steps: LiveProcessStep[]): string {
  const parsed = parseProcessLog(content)
  const summarySteps = liveStepsToSummarySteps(steps)
  const finalBody = resolveDisplayAnswer(parsed, summarySteps)
  if (parsed.hasProcess && parsed.finalAnswer.trim()) return content
  if (finalBody.trim()) return `## 最终回答\n\n${finalBody}\n`
  return content
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
  const finalizedEarlyRef = useRef(false)

  const activeSkillRef = useRef<SelectedSkillHint | undefined>(undefined)
  const userTurnRef = useRef(0)

  const finalizeAssistantReply = useCallback(
    (reply: string, processSteps: LiveProcessStep[], ownsRequest: () => boolean) => {
      if (!ownsRequest() || finalizedEarlyRef.current) return
      finalizedEarlyRef.current = true
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

  const tryEarlyShowFinal = useCallback(
    (content: string, ownsRequest: () => boolean) => {
      if (!ownsRequest() || finalizedEarlyRef.current) return
      const steps = liveStepsRef.current
      if (!isAnalysisComplete(content, steps)) return
      const reply = buildEarlyFinalizeReply(content, steps)
      if (!hasReplyReady(reply)) return
      finalizeAssistantReply(reply, steps, ownsRequest)
    },
    [finalizeAssistantReply],
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
          tryEarlyShowFinal(next.content, ownsRequest)
          return next
        })
      },
      onStep: (step: LiveProcessStep) => {
        if (!ownsRequest()) return
        liveStepsRef.current = mergeProcessStep(liveStepsRef.current, step)
        const steps = liveStepsRef.current
        setStreaming((prev) => {
          const next = prev ? { ...prev, steps } : { content: '', steps }
          if (prev?.content) tryEarlyShowFinal(prev.content, ownsRequest)
          return next
        })
      },
      onSteps: (steps: LiveProcessStep[]) => {
        if (!ownsRequest()) return
        liveStepsRef.current = steps
        setStreaming((prev) => {
          const next = prev ? { ...prev, steps } : { content: '', steps }
          if (prev?.content) tryEarlyShowFinal(prev.content, ownsRequest)
          return next
        })
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
        if (!finalizedEarlyRef.current) {
          finalizeAssistantReply(reply, processSteps, ownsRequest)
        } else if (reply) {
          setMessages((prev) => {
            const last = prev[prev.length - 1]
            if (last?.role !== 'assistant') return prev
            const stepsChanged =
              JSON.stringify(last.process_steps ?? []) !== JSON.stringify(processSteps)
            if (last.content === reply && !stepsChanged) return prev
            return [...prev.slice(0, -1), { ...last, content: reply, process_steps: processSteps }]
          })
        }
      },
    }),
    [finalizeAssistantReply, sessionId, tryEarlyShowFinal],
  )

  const recoverIncompleteReply = useCallback(
    async (
      sid: string,
      ownsRequest: () => boolean,
      tailHandlers?: ReturnType<typeof buildStreamHandlers>,
      signal?: AbortSignal,
    ): Promise<boolean> => {
      if (!ownsRequest() || finalizedEarlyRef.current) return finalizedEarlyRef.current

      try {
        let snap = await api.getProcessLog(sid)
        if (!ownsRequest() || finalizedEarlyRef.current) return finalizedEarlyRef.current

        if (snap.in_progress && tailHandlers && signal) {
          await api.tailProcessLog(sid, tailHandlers, signal, snap.log_offset)
          snap = await api.getProcessLog(sid)
        }

        if (!ownsRequest() || finalizedEarlyRef.current) return finalizedEarlyRef.current

        if (snap.reply?.trim()) {
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
      return finalizedEarlyRef.current
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
        finalizedEarlyRef.current = false
        setLoading(true)
        setStreaming({ content, steps })
        try {
          await api.tailProcessLog(id, handlers, controller.signal, snap.log_offset)
        } catch (e) {
          if (ownsRequest() && (e as Error).name !== 'AbortError') {
            setError(e instanceof Error ? e.message : '恢复过程日志失败')
          }
        }
        if (ownsRequest() && !finalizedEarlyRef.current) {
          await recoverIncompleteReply(id, ownsRequest, handlers, controller.signal)
        }
        if (ownsRequest() && !finalizedEarlyRef.current) {
          setStreaming(null)
          setLoading(false)
          setError(RESUME_INCOMPLETE_ERROR)
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

      const msgs = session.messages ?? []
      const awaitingReply = msgs[msgs.length - 1]?.role === 'user'

      setSessionId(session.id)
      activeSessionIdRef.current = session.id
      setMessages(msgs)
      setStreaming(null)
      setError(null)
      setLoading(false)
      liveStepsRef.current = []
      finalizedEarlyRef.current = false

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

      const skillForTurn = selectedSkill ?? activeSkillRef.current
      if (selectedSkill) {
        activeSkillRef.current = selectedSkill
      }
      userTurnRef.current += 1

      setLoading(true)
      setError(null)
      liveStepsRef.current = []
      streamingContentRef.current = ''
      activeSessionIdRef.current = sessionId
      userStopRef.current = false
      finalizedEarlyRef.current = false
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
        frontendTimeoutMs(text.trim(), skillForTurn?.name),
      )
      const resetStreamTimeout = (budgetSec: number) => {
        window.clearTimeout(timeoutId)
        timeoutId = window.setTimeout(
          () => controller.abort(),
          frontendTimeoutMs(text.trim(), skillForTurn?.name, budgetSec),
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
          content: text.trim(),
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, userMsg])

        await api.chatStream(
          text.trim(),
          sessionId,
          skillForTurn,
          streamHandlers,
          controller.signal,
        )
        resolvedSessionId = resolvedRef.current || resolvedSessionId

        if (ownsRequest() && !finalizedEarlyRef.current && resolvedSessionId) {
          await recoverIncompleteReply(resolvedSessionId, ownsRequest, streamHandlers, controller.signal)
        }
      } catch (e) {
        if (!ownsRequest()) return undefined
        if ((e as Error).name === 'AbortError') {
          if (userStopRef.current && !finalizedEarlyRef.current) {
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

      if (!finalizedEarlyRef.current) {
        const sid = resolvedRef.current || resolvedSessionId
        if (sid) {
          await recoverIncompleteReply(sid, ownsRequest, streamHandlers, controller.signal)
        }
      }

      if (!ownsRequest()) return undefined
      if (!finalizedEarlyRef.current) {
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
            finalizedEarlyRef.current &&
            prev.length >= 2 &&
            prev[prev.length - 1]?.role === 'assistant'
          ) {
            return prev.slice(0, -2)
          }
          return prev.slice(0, -1)
        })
        finalizedEarlyRef.current = false
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
    if (!finalizedEarlyRef.current) {
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
    finalizedEarlyRef.current = false
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
