import { useEffect, useMemo } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

const AI4DRUG_AGENT_PAGE = 'http://192.168.11.209:8888/ai4drug-pipeline.html'
const HUAXUE_AGENT_PAGE = 'http://192.168.11.209:3011/'
const DOMAIN_LEARNING_AGENT_PAGE = '/domainlearning-embed.html'
const DOMAIN_LEARNING_DIRECT_PAGE = 'http://192.168.11.209:8866/'
const DOE_AGENT_PAGE = 'http://192.168.9.116:5173/'
const BEDH_AGENT_PAGE = 'https://192.168.11.209:5173/'

type Agent = {
  id: string
  name: string
  iframeUrl: string
  externalUrl: string
}

const AGENTS: Record<string, Agent> = {
  ai4drug: {
    id: 'ai4drug',
    name: '药物研发智能体',
    iframeUrl: AI4DRUG_AGENT_PAGE,
    externalUrl: AI4DRUG_AGENT_PAGE,
  },
  huaxue: {
    id: 'huaxue',
    name: '物质科学智能体',
    iframeUrl: HUAXUE_AGENT_PAGE,
    externalUrl: HUAXUE_AGENT_PAGE,
  },
  domainlearning: {
    id: 'domainlearning',
    name: '领域学习智能体',
    iframeUrl: DOMAIN_LEARNING_AGENT_PAGE,
    externalUrl: DOMAIN_LEARNING_DIRECT_PAGE,
  },
  doe: {
    id: 'doe',
    name: 'DOE 实验设计智能体',
    iframeUrl: DOE_AGENT_PAGE,
    externalUrl: DOE_AGENT_PAGE,
  },
  bedh: {
    id: 'bedh',
    name: '数字人智能体',
    iframeUrl: BEDH_AGENT_PAGE,
    externalUrl: BEDH_AGENT_PAGE,
  },
}

export default function AgentDetailPage() {
  const { agentId } = useParams()
  const navigate = useNavigate()

  const agent = useMemo(() => (agentId ? AGENTS[agentId] : undefined), [agentId])

  // 数字人智能体仅支持新标签打开，避免 iframe 内嵌
  useEffect(() => {
    if (agentId === 'bedh') {
      window.open(BEDH_AGENT_PAGE, '_blank', 'noopener,noreferrer')
      navigate('/agents', { replace: true })
    }
  }, [agentId, navigate])

  if (agentId === 'bedh') {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-[#F9FAFB] text-sm text-slate-500">
        正在新标签页打开数字人智能体…
      </div>
    )
  }

  if (!agent) {
    return (
      <div className="flex h-full flex-1 items-center justify-center bg-[#F9FAFB]">
        <div className="px-4 text-center">
          <h1 className="mb-2 text-lg font-semibold text-gray-900">找不到智能体</h1>
          <p className="mb-4 text-sm text-gray-500">请返回智能体广场选择。</p>
          <button
            className="rounded-lg bg-[#2563EB] px-4 py-2 text-white hover:bg-[#1d4ed8]"
            onClick={() => navigate('/agents')}
          >
            返回智能体广场
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-[#F9FAFB]">
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-slate-200/60 bg-white/90 px-3 backdrop-blur-sm md:px-4">
        <div className="flex min-w-0 items-center gap-2">
          <button
            type="button"
            className="shrink-0 rounded-lg px-2 py-1.5 text-sm text-gray-600 transition hover:bg-slate-100 hover:text-gray-900"
            onClick={() => navigate('/agents')}
          >
            返回
          </button>
          <span className="truncate text-sm font-semibold text-gray-900">{agent.name}</span>
        </div>
        <a
          href={agent.externalUrl}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 rounded-lg px-2 py-1.5 text-sm text-[#2563EB] transition hover:bg-blue-50"
        >
          新标签打开
        </a>
      </div>

      <div className="min-h-0 flex-1">
        <iframe title={agent.name} src={agent.iframeUrl} className="h-full w-full border-0" />
      </div>
    </div>
  )
}
