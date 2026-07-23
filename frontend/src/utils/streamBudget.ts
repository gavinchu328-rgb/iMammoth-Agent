/** Mirror backend stream_timeouts.estimate_stream_budget (seconds → ms for fetch abort). */

const SHORT_IDLE_SEC = 5
const GENERAL_SEC = 600
const SKILL_DEFAULT_SEC = 600
const AI4DRUG_STEP_SEC = 600
const MOLECULE_BASE_SEC = 1800
const PER_MOLECULE_SEC = 600
const MAX_SEC = 7200
const TAIL_MARGIN_SEC = 120

const AI4DRUG_FAST_SKILLS = new Set(['靶点发现', '蛋白质获取', '3D构象生成'])
const AI4DRUG_STEP_SKILLS = new Set([
  '口袋预测',
  '分子对接',
  'ADMET评估',
  '受体准备',
  '配体准备',
  '对接盒配置',
  '逆合成分析',
])
const AI4DRUG_FAST_SEC = 600

function parseMoleculeCount(message: string): number | null {
  const text = message.trim()
  if (!text) return null
  const patterns = [
    /设计\s*(\d+)\s*个/,
    /生成\s*(\d+)\s*个/,
    /(\d+)\s*个候选/,
    /(\d+)\s*个分子/,
    /num_to_generate\s*[=:]\s*(\d+)/i,
    /(\d+)\s*(?:个|种)?\s*(?:小分子|分子|候选)/,
  ]
  for (const pat of patterns) {
    const m = text.match(pat)
    if (!m) continue
    const n = Number(m[1])
    if (n >= 1 && n <= 100) return n
  }
  if (['一批', '多个', '若干'].some((t) => text.includes(t))) return 8
  return null
}

export function estimateStreamBudgetSec(message: string, skillName?: string | null): number {
  const skill = (skillName || '').trim()
  const msg = message.trim()
  let total: number

  if (skill === '分子设计') {
    const n = parseMoleculeCount(msg) ?? 5
    total = MOLECULE_BASE_SEC + n * PER_MOLECULE_SEC
  } else if (skill && AI4DRUG_FAST_SKILLS.has(skill)) {
    total = AI4DRUG_FAST_SEC
  } else if (skill && AI4DRUG_STEP_SKILLS.has(skill)) {
    total = AI4DRUG_STEP_SEC
  } else if (skill) {
    total = SKILL_DEFAULT_SEC
  } else {
    total = GENERAL_SEC
  }

  return Math.min(Math.max(total, SHORT_IDLE_SEC + 30), MAX_SEC)
}

export function frontendTimeoutMs(
  message: string,
  skillName?: string | null,
  streamBudgetSec?: number | null,
): number {
  const base = streamBudgetSec ?? estimateStreamBudgetSec(message, skillName)
  return Math.round((base + TAIL_MARGIN_SEC) * 1000)
}

export function formatStreamBudgetHint(
  streamBudgetSec?: number | null,
  moleculeCount?: number | null,
): string | null {
  if (!streamBudgetSec) return null
  const min = Math.round(streamBudgetSec / 60)
  if (moleculeCount && moleculeCount > 0) {
    return `预计最长等待约 ${min} 分钟（${moleculeCount} 个分子）`
  }
  return `预计最长等待约 ${min} 分钟`
}
