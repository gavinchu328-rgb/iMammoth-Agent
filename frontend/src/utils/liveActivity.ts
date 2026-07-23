import type { LiveProcessStep } from '../api/client'
import { formatExecutedToolLabel } from './processStepUtils'

function stripPaths(text: string): string {
  return text
    .replace(/(?:~|\/home\/|\/data\d?\/|\/tmp\/|\.\/)[^\s"']+/g, (p) => {
      const base = p.replace(/\/+$/, '').split('/').pop()
      return base || '文件'
    })
    .trim()
}

export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds} 秒`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s > 0 ? `${m} 分 ${s} 秒` : `${m} 分钟`
}

export interface LiveActivity {
  title: string
  detail: string
  runningStepIndex: number | null
}

export function hasReplyReady(content: string): boolean {
  const idx = content.indexOf('## 最终回答')
  if (idx < 0) return false
  return content.slice(idx + '## 最终回答'.length).trim().length >= 8
}

export function deriveLiveActivity(
  steps: LiveProcessStep[],
  skillName?: string,
  options?: { replyReady?: boolean },
): LiveActivity {
  if (options?.replyReady) {
    return {
      title: '分析已完成',
      detail: '结果已生成，正在同步对话…',
      runningStepIndex: null,
    }
  }

  const runningIdx = steps.findIndex((s) => s.status === 'running')
  const running = runningIdx >= 0 ? steps[runningIdx] : undefined

  if (running?.kind === 'tool' || running?.kind === 'skill' || running?.kind === 'web') {
    const label = formatExecutedToolLabel(running)
    const input = stripPaths(running.input || '')
    const prefix = running.kind === 'skill' ? '正在执行技能' : '正在执行'
    return {
      title: `${prefix}：${label}`,
      detail: input ? `参数 ${input}` : running.kind === 'skill' ? '技能运行中…' : '请稍候…',
      runningStepIndex: runningIdx,
    }
  }

  if (running?.kind === 'thinking') {
    const text = stripPaths(running.result || running.input || '')
    return {
      title: skillName ? `猛犸智能体正在分析（${skillName}）` : '猛犸智能体正在分析',
      detail: text ? text.slice(0, 80) : '整理思路中…',
      runningStepIndex: runningIdx,
    }
  }

  const lastAction = [...steps].reverse().find((s) => s.kind === 'tool' || s.kind === 'skill' || s.kind === 'web')
  if (lastAction && lastAction.status !== 'running') {
    return {
      title: skillName ? `猛犸智能体正在汇总（${skillName}）` : '猛犸智能体正在汇总结果',
      detail: `已完成 ${formatExecutedToolLabel(lastAction)}，生成回复中…`,
      runningStepIndex: null,
    }
  }

  if (skillName) {
    return {
      title: `猛犸智能体正在处理：${skillName}`,
      detail: '正在连接工具并准备执行，请稍候…',
      runningStepIndex: null,
    }
  }

  return {
    title: '猛犸智能体正在思考',
    detail: '分析问题并选择合适工具…',
    runningStepIndex: null,
  }
}
