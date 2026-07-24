/**
 * 分析过程面板 — 全技能统一的尺寸与样式配置（Live / 最终展示共用）。
 * 新增技能无需改面板组件，只需在此调整全局参数。
 */

export type ProcessPanelLayoutMode = 'live' | 'final'

/** 全局尺寸 token（Tailwind class 片段） */
export const PROCESS_PANEL_LAYOUT = {
  /** Live：上方有流式正文，或收尾整理阶段 */
  liveStepListCompact: 'max-h-[min(55vh,28rem)]',
  /** Live：仅过程框、无流式正文（执行中主视图） */
  liveStepListDefault: 'max-h-[min(65vh,36rem)]',
  /** 最终消息中的过程步骤列表 */
  finalStepListMax: 'max-h-[min(48vh,18rem)]',
} as const

const SCROLL = 'overflow-y-auto overscroll-contain'

const STEP_LIST_BASE = `space-y-2 border-t border-slate-100 px-3 py-3 ${SCROLL}`

export interface ProcessStepCounts {
  stepCount: number
  thinkCount: number
  skillCount: number
  toolCount: number
}

/** 从 Live 步骤或解析步骤统计 header 所需计数。 */
export function countProcessPanelSteps(
  steps: ReadonlyArray<{ kind?: string; type?: string }>,
): ProcessStepCounts {
  let skillCount = 0
  let actionCount = 0
  for (const step of steps) {
    const kind = step.kind
    const type = step.type
    if (kind === 'skill' || type === '技能') {
      skillCount += 1
      actionCount += 1
    } else if (
      kind === 'tool' ||
      kind === 'web' ||
      type === '工具' ||
      type === '搜索'
    ) {
      actionCount += 1
    }
  }
  const stepCount = steps.length
  const thinkCount = Math.max(0, stepCount - actionCount)
  const toolCount = Math.max(0, actionCount - skillCount)
  return { stepCount, thinkCount, skillCount, toolCount }
}

export function buildProcessPanelHeader(counts: ProcessStepCounts): string {
  const { stepCount, thinkCount, skillCount, toolCount } = counts
  if (skillCount > 0) {
    return `分析过程 · ${stepCount} 步（思考 ${thinkCount} · 技能 ${skillCount} · 工具 ${toolCount}）`
  }
  if (thinkCount > 0) {
    return `分析过程 · ${stepCount} 步（思考 ${thinkCount} · 工具 ${toolCount}）`
  }
  return `分析过程 · ${toolCount} 个工具`
}

export function getProcessPanelCardClassName(): string {
  return 'overflow-hidden rounded-xl border border-slate-200/80 bg-white/80'
}

export function getProcessPanelHeaderRowClassName(): string {
  return 'flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-slate-800'
}

/** 执行中流式正文：不限高、不内滚，完整展示在过程框外。 */
export function getLiveStreamContentClassName(): string {
  return 'assistant-prose w-full text-[15px] leading-relaxed text-slate-800'
}

export interface LiveStepListLayoutOptions {
  /** 上方是否正在展示流式正文 */
  hasStreamAbove: boolean
  /** 流已结束、等待最终落盘 */
  isTailFormatting?: boolean
}

/** Live 过程步骤列表容器 class */
export function getLiveStepListClassName(options: LiveStepListLayoutOptions): string {
  const compact = options.hasStreamAbove || Boolean(options.isTailFormatting)
  const max = compact
    ? PROCESS_PANEL_LAYOUT.liveStepListCompact
    : PROCESS_PANEL_LAYOUT.liveStepListDefault
  return `${max} ${STEP_LIST_BASE}`
}

/** 最终消息 ProcessPanel 步骤列表容器 class */
export function getFinalStepListClassName(): string {
  return `${PROCESS_PANEL_LAYOUT.finalStepListMax} ${STEP_LIST_BASE}`
}

export function getLiveActivityFooterClassName(): string {
  return 'sticky bottom-0 z-10 -mx-1 mt-3 border-t border-slate-200/80 bg-slate-50/95 px-3 py-3 backdrop-blur-sm'
}
