import { useState } from 'react'
import { createPortal } from 'react-dom'
import { NavLink, useLocation } from 'react-router-dom'
import type { Session } from '../api/client'
import type { ApiLoadStatus } from '../hooks/useApiRetry'

interface Props {
  sessions: Session[]
  sessionsLoadStatus?: ApiLoadStatus
  currentSessionId?: string
  onNewChat: () => void
  onSelectSession: (id: string) => void
  onDeleteSession: (id: string) => void
  collapsed: boolean
  onToggle: () => void
}

function navItemClass(active: boolean) {
  return `flex w-full items-center justify-start gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm font-medium transition-all duration-200 cursor-pointer ${
    active
      ? 'border border-primary bg-primary text-white shadow-[0_1px_2px_rgba(15,23,42,0.06)]'
      : 'text-gray-600 hover:bg-primary/10 hover:text-primary'
  }`
}

function NavItem({
  active = false,
  onClick,
  to,
  icon,
  label,
}: {
  active?: boolean
  onClick?: () => void
  to?: string
  icon: React.ReactNode
  label: string
}) {
  const content = (
    <>
      <span className="h-4 w-4 shrink-0">{icon}</span>
      <span className="min-w-0 flex-1 text-left text-[14px] font-semibold">{label}</span>
    </>
  )

  if (to) {
    return (
      <NavLink to={to} className={({ isActive }) => navItemClass(isActive)}>
        {content}
      </NavLink>
    )
  }

  return (
    <button type="button" onClick={onClick} className={navItemClass(active)}>
      {content}
    </button>
  )
}

function formatSessionTime(iso?: string) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const y = d.getFullYear()
  const m = d.getMonth() + 1
  const day = d.getDate()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${y}.${m}.${day} ${hh}:${mm}`
}

export default function Sidebar({
  sessions,
  sessionsLoadStatus = 'ready',
  currentSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  collapsed,
  onToggle,
}: Props) {
  const location = useLocation()
  const isNewChatActive = location.pathname === '/'
  const [tooltip, setTooltip] = useState<{
    title: string
    time: string
    top: number
    left: number
  } | null>(null)

  const showSessionTooltip = (
    e: React.MouseEvent<HTMLElement>,
    title: string,
    time: string,
  ) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setTooltip({
      title,
      time,
      top: rect.top + rect.height / 2,
      left: rect.right + 8,
    })
  }

  if (collapsed) {
    return (
      <div className="flex w-12 shrink-0 flex-col items-center gap-3 border-r border-[#ECECEC] bg-[#F9FAFB] py-3">
        <button
          type="button"
          onClick={onToggle}
          className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
          title="展开侧边栏"
        >
          <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <rect width="18" height="18" x="3" y="3" rx="2" strokeWidth="2" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v18" />
          </svg>
        </button>
      </div>
    )
  }

  return (
    <aside className="flex h-full w-[320px] min-w-[320px] shrink-0 flex-col overflow-hidden border border-[#ECECEC] bg-[#F9FAFB]">
      <div className="px-3 pt-3 pb-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1">
            <img
              src="/raw.webp"
              alt="猛犸智能体"
              className="h-8 w-8 shrink-0 rounded object-contain"
            />
            <div className="min-w-0 flex-1 overflow-hidden pr-1">
              <div className="truncate text-[16px] font-bold text-[#111827] md:text-[17px]">
                猛犸智能体
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={onToggle}
            className="flex h-8 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
            title="收起侧边栏"
          >
            <svg className="h-[22px] w-[22px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4h16v16H4zM9 4v16M15 10l-2 2 2 2" />
            </svg>
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-3 pb-2">
        <nav className="flex flex-col space-y-1">
          <NavItem
            active={isNewChatActive}
            onClick={onNewChat}
            label="发起新对话"
            icon={
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
              </svg>
            }
          />
          <NavItem
            to="/skills"
            label="技能广场"
            icon={
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zm10 0a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
              </svg>
            }
          />
          <NavItem
            to="/data"
            label="数据广场"
            icon={
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7v10c0 2 1 3 3 3h10c2 0 3-1 3-3V7c0-2-1-3-3-3H7C5 4 4 5 4 7zm4 2h8M8 13h5" />
              </svg>
            }
          />
          <NavItem
            to="/agents"
            label="智能体广场"
            icon={
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" className="h-4 w-4">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 8h10M7 12h10M7 16h10M5 6a2 2 0 012-2h10a2 2 0 012 2v12a2 2 0 01-2 2H7a2 2 0 01-2-2V6z" />
              </svg>
            }
          />
        </nav>

        <div className="mx-1 my-3 border-t border-slate-200/60" />

        <div className="px-2.5 py-1.5 text-[14px] font-semibold text-gray-600">最近</div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto pb-3">
          {sessions.length === 0 && sessionsLoadStatus === 'loading' && (
            <p className="px-2.5 py-2 text-sm text-gray-400">正在加载对话记录…</p>
          )}
          {sessions.length === 0 && sessionsLoadStatus === 'error' && (
            <p className="px-2.5 py-2 text-sm text-amber-600">服务连接中，请稍候…</p>
          )}
          {sessions.length === 0 && sessionsLoadStatus === 'ready' && (
            <p className="px-2.5 py-2 text-sm text-gray-400">暂无对话记录</p>
          )}
          {sessions.map((s) => {
            const timeLabel = formatSessionTime(s.updated_at || s.created_at)
            return (
              <div
                key={s.id}
                className={`group flex w-full items-center gap-1 rounded-lg transition-all duration-200 ${
                  s.id === currentSessionId
                    ? 'bg-white font-semibold text-slate-900 shadow-sm'
                    : 'text-gray-600 hover:bg-primary/10 hover:text-primary'
                }`}
                onMouseEnter={(e) => showSessionTooltip(e, s.title, timeLabel)}
                onMouseLeave={() => setTooltip(null)}
              >
                <button
                  type="button"
                  onClick={() => onSelectSession(s.id)}
                  className="min-w-0 flex-1 truncate px-2.5 py-1.5 text-left text-sm"
                >
                  {s.title}
                </button>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm(`确定删除对话「${s.title}」？`)) {
                      onDeleteSession(s.id)
                    }
                  }}
                  className="mr-1.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100"
                  title="删除对话"
                  aria-label="删除对话"
                >
                  <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M9 7V4a1 1 0 011-1h4a1 1 0 011 1v3m-7 0h8"
                    />
                  </svg>
                </button>
              </div>
            )
          })}
        </div>
      </div>

      {tooltip &&
        createPortal(
          <div
            className="pointer-events-none fixed z-[9999] w-max max-w-[260px] -translate-y-1/2 rounded-md bg-slate-900 px-2.5 py-1.5 text-left shadow-lg"
            style={{ top: tooltip.top, left: tooltip.left }}
            role="tooltip"
          >
            <div className="text-[12px] leading-snug font-medium break-words text-white">
              {tooltip.title}
            </div>
            {tooltip.time && (
              <div className="mt-0.5 text-[11px] leading-snug text-slate-300">{tooltip.time}</div>
            )}
          </div>,
          document.body,
        )}
    </aside>
  )
}
