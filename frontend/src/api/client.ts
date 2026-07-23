export interface Skill {
  id: string
  name: string
  /** Primary category (first tag); kept for backward compatibility. */
  category: string
  /** All category tags this skill belongs to. */
  categories?: string[]
  icon: string
  description: string
  example: string
}

export interface Database {
  id: string
  name: string
  category: string
  icon: string
  description: string
  volume: string
  source_type: 'local' | 'online' | string
  example_query: string
  searchable: boolean
  project?: string
  storage_path?: string | null
  service_endpoint?: string | null
}

export interface DatabaseSearchResponse {
  database_id: string
  query: string
  searchable: boolean
  result?: Record<string, unknown> | null
  error?: string | null
  message?: string | null
  chat_prompt?: string | null
}

export interface SelectedSkillHint {
  name: string
  category?: string
  systemPrompt: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  process_steps?: LiveProcessStep[]
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages?: Message[]
}

export interface LiveProcessStep {
  kind: 'thinking' | 'tool' | 'skill' | 'web'
  title: string
  status: string
  name: string
  input: string
  result: string
  detail?: string
  tool_call_id?: string
  record_id?: string
  is_result_update?: boolean
}

export interface ProcessLogSnapshot {
  in_progress: boolean
  done: boolean
  content: string
  steps: LiveProcessStep[]
  reply: string
  error?: string | null
  log_offset: number
  stream_budget_sec?: number | null
  molecule_count?: number | null
}

export interface ChatStreamSession {
  session_id: string
  stream_budget_sec?: number | null
  molecule_count?: number | null
}

export interface ChatStreamDone {
  session_id: string
  reply: string
  error?: string | null
  steps?: LiveProcessStep[]
  ok?: boolean
  tag?: string
}

export interface ChatStreamHandlers {
  onSession?: (payload: ChatStreamSession) => void
  onDelta?: (content: string) => void
  onStep?: (step: LiveProcessStep) => void
  onDone?: (payload: ChatStreamDone) => void
  onError?: (message: string) => void
}

function parseSseBlock(block: string): { event: string; data: string } | null {
  let event = 'message'
  let data = ''
  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) event = line.slice(7).trim()
    else if (line.startsWith('data: ')) data += line.slice(6)
  }
  if (!data) return null
  return { event, data }
}

async function consumeSse(
  response: Response,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取流式响应')

  const abortIfNeeded = () => {
    if (signal?.aborted) {
      throw new DOMException('The operation was aborted', 'AbortError')
    }
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false
  let lastSessionId = ''
  let lastReply = ''

  const handleBlock = (raw: string) => {
    const parsed = parseSseBlock(raw)
    if (!parsed) return
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(parsed.data) as Record<string, unknown>
    } catch {
      return
    }
    switch (parsed.event) {
      case 'session': {
        const sid = String((payload as { session_id?: string }).session_id ?? '')
        lastSessionId = sid
        handlers.onSession?.({
          session_id: sid,
          stream_budget_sec: (payload as { stream_budget_sec?: number }).stream_budget_sec,
          molecule_count: (payload as { molecule_count?: number }).molecule_count,
        })
        break
      }
      case 'delta':
        handlers.onDelta?.(String((payload as { content?: string }).content ?? ''))
        break
      case 'step':
        handlers.onStep?.(payload as unknown as LiveProcessStep)
        break
      case 'error':
        if (signal?.aborted) break
        handlers.onError?.(String((payload as { message?: string }).message ?? '流式请求失败'))
        break
      case 'mammoth_done':
      case 'done':
        if (!finished) {
          finished = true
          lastReply = String((payload as { reply?: string }).reply ?? lastReply)
          handlers.onDone?.(payload as unknown as ChatStreamDone)
        }
        break
      default:
        break
    }
  }

  while (true) {
    abortIfNeeded()
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep = buffer.indexOf('\n\n')
    while (sep >= 0) {
      handleBlock(buffer.slice(0, sep))
      buffer = buffer.slice(sep + 2)
      sep = buffer.indexOf('\n\n')
    }
  }

  if (buffer.trim()) {
    handleBlock(buffer)
  }

  abortIfNeeded()

  if (!finished && lastSessionId && !signal?.aborted) {
    handlers.onDone?.({
      session_id: lastSessionId,
      reply: lastReply,
      error: '连接已结束但未收到完成标记',
    })
  }
}

export interface ChatResponse {
  session_id: string
  reply: string
  usage?: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
}

const BASE = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res.json()
}

export const api = {
  health: () => request<{ status: string; openclaw: boolean }>('/health'),
  skills: () => request<Skill[]>('/skills'),
  databases: () => request<Database[]>('/databases'),
  getDatabase: (id: string) => request<Database>(`/databases/${id}`),
  searchDatabase: (id: string, query: string) =>
    request<DatabaseSearchResponse>(`/databases/${id}/search`, {
      method: 'POST',
      body: JSON.stringify({ query }),
    }),
  sessions: () => request<Session[]>('/sessions'),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  getProcessLog: (id: string) => request<ProcessLogSnapshot>(`/sessions/${id}/process-log`),
  deleteSession: (id: string) => request<{ ok: boolean }>(`/sessions/${id}`, { method: 'DELETE' }),
  stopSession: (id: string, reply?: string) =>
    request<{ ok: boolean; reply: string }>(`/sessions/${id}/stop`, {
      method: 'POST',
      body: JSON.stringify({ reply: reply ?? null }),
    }),
  chat: (message: string, sessionId?: string, selectedSkill?: SelectedSkillHint) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        session_id: sessionId ?? null,
        selected_skill_name: selectedSkill?.name ?? null,
        selected_skill_system_prompt: selectedSkill?.systemPrompt ?? null,
        selected_skill_category: selectedSkill?.category ?? null,
      }),
    }),
  chatStream: async (
    message: string,
    sessionId: string | undefined,
    selectedSkill: SelectedSkillHint | undefined,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
  ) => {
    const res = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        session_id: sessionId ?? null,
        selected_skill_name: selectedSkill?.name ?? null,
        selected_skill_system_prompt: selectedSkill?.systemPrompt ?? null,
        selected_skill_category: selectedSkill?.category ?? null,
      }),
      signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || '请求失败')
    }
    await consumeSse(res, handlers, signal)
  },
  tailProcessLog: async (
    sessionId: string,
    handlers: ChatStreamHandlers,
    signal?: AbortSignal,
    afterBytes = 0,
  ) => {
    const res = await fetch(
      `${BASE}/sessions/${sessionId}/process-log/stream?after=${Math.max(0, afterBytes)}`,
      { signal },
    )
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || '无法恢复过程日志')
    }
    await consumeSse(res, handlers, signal)
  },
}
