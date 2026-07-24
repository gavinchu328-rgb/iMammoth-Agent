/**
 * Live activity phase tests.
 * Run: cd frontend && npx --yes tsx ../scripts/test_live_activity.ts
 */
import {
  deriveLiveActivity,
  deriveLiveActivityPhase,
  isAnalysisComplete,
  isLivePanelTailFormatting,
} from '../frontend/src/utils/liveActivity'
import type { LiveProcessStep } from '../frontend/src/api/client'

function step(partial: Partial<LiveProcessStep> & Pick<LiveProcessStep, 'kind' | 'title'>): LiveProcessStep {
  return {
    status: 'done',
    name: partial.title,
    input: '',
    result: '',
    ...partial,
  }
}

let failed = 0

function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

const running: LiveProcessStep[] = [
  step({ kind: 'tool', title: '分子设计', status: 'running', name: '分子设计' }),
]
assert(deriveLiveActivityPhase(running) === 'running', 'running step → running phase')
assert(deriveLiveActivity(running).title.includes('正在执行'), 'running step activity title')

const doneMidPipeline: LiveProcessStep[] = [
  step({ kind: 'tool', title: '口袋预测', name: '口袋预测', result: '识别 1 个口袋' }),
]
assert(
  deriveLiveActivityPhase(doneMidPipeline, { streamFinalReady: false }) === 'idle',
  'single done tool mid-pipeline stays idle',
)
const midActivity = deriveLiveActivity(doneMidPipeline, '分子设计', { streamFinalReady: false })
assert(midActivity.title.includes('正在处理'), 'mid-pipeline shows skill processing not summarizing')
assert(!midActivity.title.includes('汇总'), 'mid-pipeline must not show summarizing')
assert(midActivity.detail === '', 'mid-pipeline has no secondary status line')

const readyContent = '## 最终回答\n\n| 口袋 | 评分 |\n| --- | --- |'
const tailSteps = doneMidPipeline
assert(isLivePanelTailFormatting(readyContent, tailSteps), 'tail formatting when stream done and idle tools')
assert(
  isLivePanelTailFormatting('', tailSteps, {
    streamRaw: readyContent,
    awaitingFinalize: true,
  }),
  'tail formatting from raw stream when display content empty',
)
assert(
  deriveLiveActivityPhase(tailSteps, { streamFinalReady: true }) === 'formatting',
  'stream done → formatting tail',
)
const tailActivity = deriveLiveActivity(tailSteps, undefined, { streamFinalReady: true })
assert(tailActivity.title === '正在整理最终结果', 'tail formatting title')
assert(!tailActivity.title.includes('结果已就绪'), 'live panel never shows 结果已就绪')

assert(
  !isLivePanelTailFormatting('', tailSteps),
  'no tail formatting before stream final',
)
assert(
  !isLivePanelTailFormatting(readyContent, []),
  'no tail formatting when stream has final but no real tool steps',
)

const preambleOnly = '好的，我来帮您分析这个分子的对接结果。'
assert(
  !isAnalysisComplete(preambleOnly, []),
  'preamble without marker or steps must not early-finalize',
)
assert(
  isAnalysisComplete(readyContent, tailSteps),
  'explicit final marker completes when tools idle',
)
const richBodyNoMarker =
  '| 对接分数 | -7.5 kcal/mol |\n| --- | --- |\n\n结合能较好，建议进一步优化侧链。'
assert(
  !isAnalysisComplete(richBodyNoMarker, []),
  'rich body without marker or completed tools must not early-finalize',
)
assert(
  isAnalysisComplete(richBodyNoMarker, tailSteps),
  'rich body with completed tools may finalize without marker',
)

console.log('='.repeat(60))
if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: live activity phases')
process.exit(0)
