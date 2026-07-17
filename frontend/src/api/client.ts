export interface Skill {
  id: string
  name: string
  category: string
  icon: string
  description: string
  example: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  messages?: Message[]
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
  sessions: () => request<Session[]>('/sessions'),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  deleteSession: (id: string) => request<{ ok: boolean }>(`/sessions/${id}`, { method: 'DELETE' }),
  chat: (message: string, sessionId?: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId ?? null }),
    }),
}
