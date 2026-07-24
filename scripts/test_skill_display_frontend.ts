/**
 * Frontend skill summary tests — mirrors scripts/test_skill_display_pipeline.py fixtures.
 * Run: cd frontend && npx --yes tsx ../scripts/test_skill_display_frontend.ts
 */
import {
  buildFallbackFinalAnswer,
  formatActionStepSummaryBlock,
  type ProcessStep,
} from '../frontend/src/utils/parseProcessLog'
import { isJsonLikeToolOutput } from '../frontend/src/utils/processStepUtils'
import { resolveStreamingDisplayContent, stripStreamingNoise } from '../frontend/src/utils/streamingDisplay'

const partialCases = ['## 分析', '分析', '## ', '分析过程']
for (const partial of partialCases) {
  const cleaned = stripStreamingNoise(partial)
  if (cleaned) {
    throw new Error(`partial process leak: ${JSON.stringify(partial)} -> ${JSON.stringify(cleaned)}`)
  }
  const live = resolveStreamingDisplayContent(partial, { hasLiveSteps: true, hasProcess: false })
  if (live) {
    throw new Error(`partial process in live stream: ${JSON.stringify(partial)} -> ${JSON.stringify(live)}`)
  }
}
console.log('PASS  partial process stream filter')

import { looksLikeModelPipelineChecklist } from '../frontend/src/utils/streamingDisplay'

const pipelineNoise = `**3D构象生成**

- EGFR_3W2S_pocket1_mol0 · CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl

**配体准备**

- EGFR_3W2S_pocket1_mol0 · PDBQT 已生成

molecular_docking

等待执行...

molecular_docking

✅ 步骤 6 完成：配体准备成功。`
if (!looksLikeModelPipelineChecklist(pipelineNoise)) {
  throw new Error('pipeline checklist should be detected as noise')
}
if (stripStreamingNoise(pipelineNoise)) {
  throw new Error('pipeline checklist should be stripped from stream')
}
console.log('PASS  pipeline checklist stream filter')

type Case = {
  skill: string
  title: string
  result: string
  detail: string
  needles: string[]
}

const CASES: Case[] = [
  {
    skill: '靶点发现',
    title: '靶点发现',
    result: '发现 2 个靶点，Top EGFR',
    detail: 'EGFR · 关联分 0.912 · PDB 3W2S',
    needles: ['EGFR', '关联'],
  },
  {
    skill: '蛋白质获取',
    title: '蛋白质获取',
    result: 'EGFR · PDB 3W2S',
    detail: 'EGFR · PDB 3W2S · EGFR_3W2S · 结构已清洗',
    needles: ['EGFR', 'PDB'],
  },
  {
    skill: '口袋预测',
    title: '口袋预测',
    result: '识别 1 个结合口袋',
    detail: 'EGFR_3W2S_pocket1 · 评分 0.82 · 概率 0.91',
    needles: ['pocket', '评分'],
  },
  {
    skill: '分子设计',
    title: '分子设计',
    result: '已生成 2 个候选分子',
    detail: '1. mol1 · CCO\n2. mol2 · CCN',
    needles: ['mol', 'CCO'],
  },
  {
    skill: '3D构象生成',
    title: '3D构象生成',
    result: '已生成 1 个分子构象',
    detail: 'EGFR_3W2S_pocket1_mol0 · 5 个构象 · CCO',
    needles: ['构象', 'mol0'],
  },
  {
    skill: '受体准备',
    title: '受体准备',
    result: '已制备 1 个受体',
    detail: 'EGFR_3W2S · 受体 PDBQT 已生成',
    needles: ['受体', 'PDBQT'],
  },
  {
    skill: '配体准备',
    title: '配体准备',
    result: '已制备 1 个配体',
    detail: 'EGFR_3W2S_pocket1_mol0 · PDBQT 已生成',
    needles: ['配体', 'PDBQT'],
  },
  {
    skill: '对接盒配置',
    title: '对接盒配置',
    result: '已配置 1 个对接盒',
    detail: 'EGFR_3W2S_pocket1 · 中心 (10.0, 20.0, 30.0) · 尺寸 20.0×20.0×20.0 Å',
    needles: ['对接', '中心'],
  },
  {
    skill: '分子对接',
    title: '分子对接',
    result: '分子对接完成，最佳 -8.200 kcal/mol',
    detail: 'EGFR_3W2S_pocket1_mol0 · EGFR_3W2S_pocket1 · 打分 -8.200 kcal/mol',
    needles: ['对接', '打分'],
  },
  {
    skill: 'ADMET评估',
    title: 'ADMET 评估',
    result: '已评估 1 个分子 ADMET',
    detail: 'gefitinib_mol0 · QED 0.72 · BBB 0.15 · hERG 0.31',
    needles: ['QED', 'gefitinib'],
  },
  {
    skill: '逆合成分析',
    title: '逆合成分析',
    result: '已生成 2 条合成路线',
    detail: '路线1 · 评分 0.88 · 4 步\n路线2 · 评分 0.75 · 2 步',
    needles: ['路线', '合成'],
  },
]

function stepFrom(c: Case, displayBlock?: string): ProcessStep & { displayBlock?: string } {
  return {
    index: 1,
    title: c.title,
    type: '工具',
    status: '已完成',
    name: c.title,
    inputSummary: '',
    resultSummary: c.result,
    detail: c.detail,
    displayBlock,
  }
}

function assertNoJson(text: string, label: string) {
  if (!text.trim()) throw new Error(`${label}: empty`)
  if (isJsonLikeToolOutput(text)) throw new Error(`${label}: JSON leak`)
  if (text.includes('"success"') && text.includes('{')) throw new Error(`${label}: JSON fragment`)
}

let failed = 0
for (const c of CASES) {
  try {
    const step = stepFrom(c)
    const block = formatActionStepSummaryBlock(step)
    if (!block) throw new Error('no summary block')
    assertNoJson(block, 'block')

    const fromDisplayBlock = formatActionStepSummaryBlock(stepFrom(c, block))
    if (fromDisplayBlock !== block) throw new Error('displayBlock not preferred')

    const jsonStep = {
      ...step,
      detail: '{"tool":"x","molecules":[{"id":"a"}]}',
      resultSummary: '{"success":true}',
    }
    const jsonBlock = formatActionStepSummaryBlock(jsonStep)
    if (jsonBlock && isJsonLikeToolOutput(jsonBlock)) {
      throw new Error('JSON step produced JSON block')
    }

    const fallback = buildFallbackFinalAnswer([step])
    assertNoJson(fallback, 'fallback')
    const low = fallback.toLowerCase()
    if (!c.needles.some((n) => low.includes(n.toLowerCase()) || fallback.includes(n))) {
      throw new Error(`missing needles ${c.needles.join(', ')} in ${fallback.slice(0, 120)}`)
    }

    const stream = resolveStreamingDisplayContent(`## 最终回答\n\n${fallback}`, {
      hasLiveSteps: true,
      hasProcess: true,
      parsedFinalAnswer: fallback,
    })
    assertNoJson(stream || '', 'stream')
    if (!stream?.trim()) throw new Error('empty stream display')

    console.log(`PASS  ${c.skill}`)
  } catch (e) {
    failed += 1
    console.log(`FAIL  ${c.skill}: ${e instanceof Error ? e.message : e}`)
  }
}

console.log('='.repeat(60))
console.log(`${CASES.length - failed}/${CASES.length} passed`)
process.exit(failed > 0 ? 1 : 0)
