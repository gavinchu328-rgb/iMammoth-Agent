/**
 * Run: npx --yes tsx scripts/test_process_panel_layout.ts
 */
import {
  buildProcessPanelHeader,
  countProcessPanelSteps,
  getLiveStepListClassName,
  getLiveStreamContentClassName,
  PROCESS_PANEL_LAYOUT,
} from '../frontend/src/utils/processPanelLayout'

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
assert(!streamCls.includes('max-h-'), 'stream content should not be height-limited')

const compact = getLiveStepListClassName({ hasStreamAbove: true })
const roomy = getLiveStepListClassName({ hasStreamAbove: false })
assert(compact.includes(PROCESS_PANEL_LAYOUT.liveStepListCompact), compact)
assert(roomy.includes(PROCESS_PANEL_LAYOUT.liveStepListDefault), roomy)
assert(compact !== roomy, 'compact vs default differ')

const tail = getLiveStepListClassName({ hasStreamAbove: false, isTailFormatting: true })
assert(tail.includes(PROCESS_PANEL_LAYOUT.liveStepListCompact), tail)

if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: process panel layout')
