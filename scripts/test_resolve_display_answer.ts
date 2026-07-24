/**
 * Run: npx --yes tsx scripts/test_resolve_display_answer.ts
 */
import {
  buildFallbackFinalAnswer,
  resolveDisplayAnswer,
} from '../frontend/src/utils/parseProcessLog'

const pocketTable = `**识别 3 个结合口袋，主口袋 EGFR_3W2S_pocket1**

| 口袋 ID | 评分 | 概率 |
| --- | --- | --- |
| EGFR_3W2S_pocket1 | 0.82 | 0.91 |
| EGFR_3W2S_pocket2 | 0.71 | 0.85 |`

const modelShort = '已完成口袋预测，EGFR 上识别到 3 个潜在结合口袋，推荐优先关注 pocket1。'

const steps = [
  {
    type: '工具' as const,
    title: '口袋预测',
    name: '口袋预测',
    resultSummary: '识别 3 个结合口袋',
    detail: 'EGFR_3W2S_pocket1 · 评分 0.82 · 概率 0.91',
    displayBlock: pocketTable,
  },
]

let failed = 0
function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

// Decoupled: usable model final wins; no merge with step table.
const withModel = resolveDisplayAnswer(
  { hasProcess: true, finalAnswer: modelShort, raw: '' },
  steps,
)
assert(withModel === modelShort, 'model final kept when usable (no step merge)')
assert(!withModel.includes('| EGFR_3W2S_pocket1 |'), 'step table not merged into model final')

// Empty / unusable model → step synthesis fallback.
const fromSteps = buildFallbackFinalAnswer(steps)
assert(fromSteps.includes('pocket1'), 'displayBlock used in fallback')

const noModel = resolveDisplayAnswer({ hasProcess: true, finalAnswer: '', raw: '' }, steps)
assert(noModel.includes('| EGFR_3W2S_pocket1 |'), 'fallback to steps when model final missing')

console.log(failed === 0 ? 'ok: resolve display answer' : `failed: ${failed}`)
process.exit(failed > 0 ? 1 : 0)
