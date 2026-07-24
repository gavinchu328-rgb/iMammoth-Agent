/**
 * Run: npx --yes tsx scripts/test_parse_stream_process_steps.ts
 */
import { parseStreamProcessLiveSteps } from '../frontend/src/utils/parseProcessLog'

let failed = 0
function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

const stream = `## 分析过程
- 工具数: 3

### 步骤 1 · 深度思考
- 类型: 思考
- 状态: 已执行
- 名称: 深度思考
- 输入摘要: 用户要求配置对接盒
- 结果摘要: 需执行 protein_acquisition

### 步骤 2 · protein_acquisition
- 类型: 工具
- 状态: 已执行
- 名称: protein_acquisition
- 输入摘要: EGFR_3W2S
- 结果摘要: 成功

## 最终回答

对接盒配置完成。`

const steps = parseStreamProcessLiveSteps(stream)
assert(steps.length === 2, `expected 2 steps, got ${steps.length}`)
assert(steps[1].name === 'protein_acquisition', steps[1].name)
assert(parseStreamProcessLiveSteps('').length === 0, 'empty')

if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: parse stream process steps')
