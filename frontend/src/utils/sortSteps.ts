import type { LiveProcessStep } from '../api/client'

/** 已完成步骤保持原序，进行中的步骤统一排到末尾，避免并行工具先完成时顺序错乱。 */
export function sortStepsForDisplay(steps: LiveProcessStep[]): LiveProcessStep[] {
  const done: LiveProcessStep[] = []
  const running: LiveProcessStep[] = []
  for (const step of steps) {
    if (step.status === 'running') running.push(step)
    else done.push(step)
  }
  return [...done, ...running]
}
