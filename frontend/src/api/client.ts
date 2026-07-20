export interface Skill {
  id: string
  name: string
  category: string
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
  kind: 'thinking' | 'tool'
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

export interface ChatStreamDone {
  session_id: string
  reply: string
  error?: string | null
  steps?: LiveProcessStep[]
  ok?: boolean
  tag?: string
}

export interface ChatStreamHandlers {
  onSession?: (sessionId: string) => void
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
): Promise<void> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('无法读取流式响应')

  const decoder = new TextDecoder()
  let buffer = ''
  let finished = false

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep = buffer.indexOf('\n\n')
    while (sep >= 0) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const parsed = parseSseBlock(raw)
      if (parsed) {
        const payload = JSON.parse(parsed.data)
        switch (parsed.event) {
          case 'session':
            handlers.onSession?.(payload.session_id)
            break
          case 'delta':
            handlers.onDelta?.(payload.content ?? '')
            break
          case 'step':
            handlers.onStep?.(payload as LiveProcessStep)
            break
          case 'error':
            handlers.onError?.(payload.message ?? '流式请求失败')
            break
          case 'mammoth_done':
          case 'done':
            // mammoth_done / done 可能各发一次，只处理一次
            if (!finished) {
              finished = true
              handlers.onDone?.(payload as ChatStreamDone)
            }
            break
          default:
            break
        }
      }
      sep = buffer.indexOf('\n\n')
    }
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
  deleteSession: (id: string) => request<{ ok: boolean }>(`/sessions/${id}`, { method: 'DELETE' }),
  chat: (message: string, sessionId?: string, selectedSkill?: SelectedSkillHint) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({
        message,
        session_id: sessionId ?? null,
        selected_skill_name: selectedSkill?.name ?? null,
        selected_skill_system_prompt: selectedSkill?.systemPrompt ?? null,
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
      }),
      signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || '请求失败')
    }
    await consumeSse(res, handlers)
  },
}
