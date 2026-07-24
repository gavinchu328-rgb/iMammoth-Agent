import type { SelectedSkillHint } from '../api/client'

/** 用户自由输入与上一轮已选技能明显冲突时，不再继承 sticky skill。 */
export function messageConflictsWithSkill(message: string, skillName: string): boolean {
  const t = (message || '').trim()
  const skill = (skillName || '').trim()
  if (!t || !skill) return false

  const wantsProtein = /获取.*蛋白|蛋白.*三维|三维结构|protein_acquisition|EGFR_\w{4}/i.test(t) && /蛋白/.test(t)
  const wantsTarget = /药物靶点|找.*靶点|target_discover/i.test(t) && /靶点|肺癌|疾病/.test(t)
  const wantsPocket = /口袋|pocket_prediction|结合口袋/i.test(t)
  const wantsDocking = /分子对接|molecular_docking|对接打分/i.test(t)
  const wantsLigand = /配体准备|ligand_preparation|pdbqt/i.test(t)
  const wantsRetrosynth = /逆合成|retrosynth|怎么合成/i.test(t)
  const wantsAdmet = /admet|吸收|代谢|毒性/i.test(t)

  if (skill === '靶点发现' && wantsProtein) return true
  if (skill === '蛋白质获取' && wantsTarget) return true
  if (skill === '靶点发现' && wantsPocket && !wantsTarget) return true
  if (skill === '靶点发现' && wantsDocking) return true
  if (skill === '靶点发现' && wantsLigand) return true
  if (skill === '靶点发现' && wantsRetrosynth) return true
  if (skill === '靶点发现' && wantsAdmet) return true
  if (skill === '蛋白质获取' && wantsRetrosynth) return true
  if (skill === '逆合成分析' && wantsProtein) return true

  return false
}

export function resolveSkillForTurn(
  message: string,
  selectedSkill?: SelectedSkillHint,
  stickySkill?: SelectedSkillHint,
): SelectedSkillHint | undefined {
  if (selectedSkill) return selectedSkill
  if (stickySkill && !messageConflictsWithSkill(message, stickySkill.name)) {
    return stickySkill
  }
  return undefined
}
