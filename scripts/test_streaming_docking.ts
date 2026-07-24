/**
 * Run: npx --yes tsx scripts/test_streaming_docking.ts
 */
import {
  looksLikeModelPipelineChecklist,
  stripEmbeddedProcessTemplateBlocks,
  stripStreamingNoise,
} from '../frontend/src/utils/streamingDisplay'

let failed = 0
function assert(cond: boolean, msg: string) {
  if (!cond) {
    failed += 1
    console.log(`FAIL  ${msg}`)
  }
}

const dockingStep = `## 分析过程
- 工具数: 7

### 步骤 1 · 获取蛋白结构
- 类型: 工具
- 状态: 进行中

✅ **步骤 1：蛋白结构获取完成**
- Target: EGFR_3W2S (PDB: 3W2S)
- 报告: [查看报告](http://192.168.11.209:9092/ai4drug-reports/x.md)

✅ **步骤 7：分子对接完成**
- Docking Score: **-7.922 kcal/mol**`

assert(!looksLikeModelPipelineChecklist(dockingStep), 'docking step narrative is not checklist noise')

const cleaned = stripStreamingNoise(dockingStep)
assert(cleaned.includes('蛋白结构获取完成'), cleaned)
assert(cleaned.includes('kcal/mol'), cleaned)
assert(!cleaned.includes('- 类型:'), cleaned)

const withTemplate = `✅ **步骤 4：对接盒配置完成**
- Pocket: EGFR_3W2S_pocket1

### 步骤 4 · 对接盒配置
- 类型: 工具
- 状态: 已执行`

const stripped = stripEmbeddedProcessTemplateBlocks(withTemplate)
assert(stripped.includes('对接盒配置完成'), stripped)
assert(!stripped.includes('- 类型:'), stripped)

const waitingNoise = `molecular_docking\n\n等待执行...\n\n✅ 步骤 6 完成：配体准备成功。`
assert(looksLikeModelPipelineChecklist(waitingNoise), 'waiting checklist still noise')
assert(!stripStreamingNoise(waitingNoise), 'waiting checklist stripped')

if (failed > 0) {
  console.log(`failed: ${failed}`)
  process.exit(1)
}
console.log('ok: docking stream display')
