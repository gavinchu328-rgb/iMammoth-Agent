import type { Skill } from '../api/client'

/** All category tags for a skill (supports multi-tag skills). */
export function skillCategories(skill: Skill): string[] {
  if (skill.categories?.length) return skill.categories
  return skill.category ? [skill.category] : []
}

/** Collect unique category tags from a skill list, preserving first-seen order. */
export function collectSkillCategoryTags(skills: Skill[]): string[] {
  const seen = new Set<string>()
  const tags: string[] = []
  for (const skill of skills) {
    for (const cat of skillCategories(skill)) {
      if (!seen.has(cat)) {
        seen.add(cat)
        tags.push(cat)
      }
    }
  }
  return tags
}

/** Whether a skill appears under the given category tab (「全部」 matches all). */
export function skillMatchesCategory(skill: Skill, category: string): boolean {
  if (category === '全部') return true
  return skillCategories(skill).includes(category)
}
