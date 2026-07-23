import type { BackendHealth } from '../hooks/useBackendHealth'

export default function BackendStatusBanner({ health }: { health: BackendHealth }) {
  if (health === 'up' || health === 'checking') return null

  return (
    <div className="shrink-0 border-b border-red-200 bg-red-50 px-4 py-2 text-center text-sm text-red-700">
      后端服务未连接，技能/数据/历史对话暂时无法加载。系统正在自动重试，请稍候或联系管理员执行{' '}
      <code className="rounded bg-red-100 px-1">./scripts/service.sh restart</code>
    </div>
  )
}
