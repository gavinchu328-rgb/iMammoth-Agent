/**
 * Run: npx --yes tsx scripts/test_process_panel_layout.ts
 */
import {
  buildProcessPanelHeader,
  countProcessPanelSteps,
  getLiveStepListClassName,
  getLiveStreamContentClassName,
  PROCESS_PANEL_LAYOUT,
  resolveLiveSummaryDisplay,
} from '../frontend/src/utils/processPanelLayout'
import { looksLikeModelPipelineChecklist } from '../frontend/src/utils/streamingDisplay'

let failed = 0
function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

const counts = countProcessPanelSteps([
  { kind: 'thinking' },
  { kind: 'tool' },
  { kind: 'tool', title: '口袋预测' },
])
assert(counts.stepCount === 3, 'step count')
assert(counts.thinkCount === 1, 'think count')
assert(counts.toolCount === 2, 'tool count')

const header = buildProcessPanelHeader(counts)
assert(header.includes('分析过程'), header)
assert(header.includes('思考 1'), header)

const streamCls = getLiveStreamContentClassName()
assert(streamCls.includes('assistant-prose'), streamCls)
assert(!streamCls.includes('max-h-'), 'stream content must stay outside the capped process box')
assert(!streamCls.includes('overflow-y-auto'), streamCls)

const liveSteps = getLiveStepListClassName()
const liveStepsTail = getLiveStepListClassName({ isTailFormatting: true })
assert(liveSteps.includes(PROCESS_PANEL_LAYOUT.liveStepListMax), liveSteps)
assert(liveStepsTail.includes(PROCESS_PANEL_LAYOUT.liveStepListMax), liveStepsTail)
assert(liveSteps === liveStepsTail, 'live step list height is unified across phases')

const ligandStream = '✅ 第 2 步：配体准备完成。PDBQT 配体文件已生成。'
const shown = resolveLiveSummaryDisplay(ligandStream, looksLikeModelPipelineChecklist)
assert(shown === ligandStream, 'stream stays visible regardless of process steps')

const pipeline = 'conformer_generation 等待执行\n步骤 1 完成'
assert(resolveLiveSummaryDisplay(pipeline, looksLikeModelPipelineChecklist) === '', 'pipeline checklist hidden')

if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: process panel layout')
