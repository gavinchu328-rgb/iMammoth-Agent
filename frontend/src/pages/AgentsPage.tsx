import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { CSSProperties } from 'react'

const AI4DRUG_AGENT_PAGE = 'http://192.168.11.209:8888/ai4drug-pipeline.html'
const HUAXUE_AGENT_PAGE = 'http://192.168.11.209:3011/'
const DOMAIN_LEARNING_AGENT_PAGE = 'http://192.168.11.209:8866/'

type AgentCard = {
  id: string
  name: string
  category: string
  icon: string
  description: string
  detailPath: string
  externalUrl?: string
  disabled?: boolean
}

export default function AgentsPage() {
  const navigate = useNavigate()
  const agents = useMemo<AgentCard[]>(
    () => [
      {
        id: 'ai4drug',
        name: '药物研发智能体',
        category: '药物研发',
        icon: '💊',
        description: '端到端药物发现工作流（对接 / 结构预测 / 分子设计）',
        detailPath: '/agents/ai4drug',
        externalUrl: AI4DRUG_AGENT_PAGE,
      },
      {
        id: 'huaxue',
        name: '物质科学智能体',
        category: '物质科学',
        icon: '⚛️',
        description: '物质科学与化学研究智能体（材料 / 反应 / 实验分析）',
        detailPath: '/agents/huaxue',
        externalUrl: HUAXUE_AGENT_PAGE,
      },
      {
        id: 'domainlearning',
        name: '领域学习智能体',
        category: '领域学习',
        icon: '📚',
        description: '领域知识学习与问答智能体（文献 / 协议 / 专业知识）',
        detailPath: '/agents/domainlearning',
        externalUrl: DOMAIN_LEARNING_AGENT_PAGE,
      },
      {
        id: 'coming-soon-1',
        name: '实验流程助手',
        category: '通用能力',
        icon: '🧪',
        description: '敬请期待：将逐步接入更多实验类模块',
        detailPath: '/agents/ai4drug',
        disabled: true,
      },
      {
        id: 'coming-soon-2',
        name: '数据分析助手',
        category: '数据分析',
        icon: '📊',
        description: '敬请期待：将逐步接入更多数据分析模块',
        detailPath: '/agents/ai4drug',
        disabled: true,
      },
    ],
    [],
  )

  const categories = ['全部', ...Array.from(new Set(agents.map((a) => a.category)))]
  const [active, setActive] = useState('全部')

  const filtered = active === '全部' ? agents : agents.filter((a) => a.category === active)

  return (
    <div className="flex-1 overflow-y-auto">
      <main className="mx-auto w-full max-w-7xl px-3 py-6 pb-16 md:px-8 md:py-10">
        <div className="mb-6">
          <h1 className="text-xl font-extrabold text-slate-900 md:text-2xl">智能体广场</h1>
          <p className="mt-1 text-sm text-[#666666]">点击卡片进入对应智能体页面</p>
        </div>

        <div className="mb-4 flex min-w-max flex-nowrap justify-start gap-2 overflow-x-auto md:flex-wrap md:justify-start md:gap-3">
          {categories.map((cat) => {
            const isActive = active === cat
            return (
              <button
                key={cat}
                type="button"
                onClick={() => setActive(cat)}
                className={`group relative flex cursor-pointer items-center justify-center px-3 py-2 text-sm whitespace-nowrap transition-all duration-300 select-none md:px-4 ${
                  isActive ? 'font-bold text-slate-900' : 'font-medium text-[#666666]'
                }`}
              >
                <span>{cat}</span>
              </button>
            )
          })}
        </div>

        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 md:gap-3 lg:grid-cols-3">
          {filtered.map((a) => {
            const disabled = !!a.disabled
            const style: CSSProperties = disabled ? { opacity: 0.7 } : {}
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => {
                  if (disabled) return
                  navigate(a.detailPath)
                }}
                className="group flex h-full cursor-pointer flex-col items-start gap-3 rounded-[20px] border border-[#E5E5E5] bg-[radial-gradient(60%_60%_at_100%_100%,_#E1EAFF_0%,_#FFFFFF_100%)] p-4 text-left transition-all duration-300 hover:border-slate-200 hover:shadow-md active:scale-[1.02] md:p-5"
                style={style}
                title={disabled ? '敬请期待' : '进入页面'}
              >
                <div className="flex items-center gap-2">
                  <div className="flex size-7 shrink-0 items-center justify-center rounded-full border-[#2563EB] bg-[#2563EB]/15 text-base">
                    {a.icon}
                  </div>
                  <span className="text-sm font-normal text-black md:text-base">{a.name}</span>
                </div>
                <p className="line-clamp-2 text-xs leading-relaxed break-all text-[#666666] md:text-sm">
                  {a.description}
                </p>
                {a.externalUrl && !disabled && (
                  <a
                    href={a.externalUrl}
                    target="_blank"
                    rel="noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    className="text-xs font-medium text-[#2563EB] hover:text-[#1d4ed8]"
                  >
                    打开外部页面（新标签）
                  </a>
                )}
                {disabled && <span className="text-xs text-gray-400">即将接入</span>}
              </button>
            )
          })}
        </div>
      </main>
    </div>
  )
}
