/**
 * Run: npx --yes tsx scripts/test_skill_routing.ts
 */
import {
  messageConflictsWithSkill,
  resolveSkillForTurn,
} from '../frontend/src/utils/skillRouting'
import type { SelectedSkillHint } from '../frontend/src/api/client'

let failed = 0
function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

const targetSticky: SelectedSkillHint = {
  name: '靶点发现',
  category: 'AI4Drug',
  systemPrompt: 'target',
}

assert(
  messageConflictsWithSkill('帮我获取 EGFR_3W2S 蛋白的三维结构信息', '靶点发现'),
  'protein query conflicts with sticky 靶点发现',
)
assert(
  !messageConflictsWithSkill('再帮我多找几个肺癌靶点', '靶点发现'),
  'follow-up target query keeps 靶点发现',
)
assert(
  resolveSkillForTurn('再帮我多找几个肺癌靶点', undefined, targetSticky) === targetSticky,
  'same-skill follow-up keeps sticky hint',
)
assert(
  resolveSkillForTurn('帮我获取 EGFR_3W2S 蛋白的三维结构信息', undefined, targetSticky) === undefined,
  'topic switch drops sticky 靶点发现',
)

if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: skill routing')
