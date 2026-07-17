import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type Skill } from '../api/client'
import SkillPlaza from '../components/SkillPlaza'

export default function SkillsPage() {
  const navigate = useNavigate()
  const [skills, setSkills] = useState<Skill[]>([])

  useEffect(() => {
    api.skills().then(setSkills).catch(console.error)
  }, [])

  const handleSelect = (skill: Skill) => {
    navigate('/', { state: { prompt: skill.example.trim() } })
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <main className="mx-auto w-full max-w-7xl px-3 py-6 pb-16 md:px-8 md:py-10">
        <div className="mb-6">
          <h1 className="text-xl font-extrabold text-slate-900 md:text-2xl">技能广场</h1>
          <p className="mt-1 text-sm text-[#666666]">选择技能快速开始，或在对话中直接描述您的需求</p>
        </div>
        <SkillPlaza skills={skills} onSelect={handleSelect} showTitle={false} />
      </main>
    </div>
  )
}
