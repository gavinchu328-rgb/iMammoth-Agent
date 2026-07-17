import { useState } from 'react'
import type { Skill } from '../api/client'

interface Props {
  skills: Skill[]
  onSelect: (skill: Skill) => void
  compact?: boolean
  showTitle?: boolean
}

function FileTextIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="size-4"
      aria-hidden="true"
    >
      <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z" />
      <path d="M14 2v4a2 2 0 0 0 2 2h4" />
      <path d="M10 9H8" />
      <path d="M16 13H8" />
      <path d="M16 17H8" />
    </svg>
  )
}

export default function SkillPlaza({ skills, onSelect, compact = false, showTitle = true }: Props) {
  const categories = ['全部', ...Array.from(new Set(skills.map((s) => s.category)))]
  const [active, setActive] = useState('全部')

  const filtered = active === '全部' ? skills : skills.filter((s) => s.category === active)

  return (
    <div className={compact ? 'w-full' : ''}>
      {showTitle && (
        <div className="mb-4">
          <h2 className="text-base font-bold text-slate-900">技能广场</h2>
        </div>
      )}

      <div className="animate-slide-up mx-auto mb-4 flex min-w-max flex-nowrap justify-start gap-2 overflow-x-auto px-1 md:flex-wrap md:justify-center md:gap-3 md:px-0">
        {categories.map((cat) => {
          const isActive = active === cat
          return (
            <button
              key={cat}
              type="button"
              onClick={() => setActive(cat)}
              className={`group relative flex cursor-pointer items-center justify-center px-3 py-2 text-sm whitespace-nowrap transition-all duration-300 select-none md:px-4 ${
                isActive ? 'font-bold text-slate-900' : 'font-medium text-[#666666]'
              }`}
            >
              <span>{cat}</span>
            </button>
          )
        })}
      </div>

      <div className="animate-slide-up mx-auto w-full max-w-5xl px-1">
        <div className="grid grid-cols-1 gap-2 transition-all md:grid-cols-2 md:gap-3 lg:grid-cols-3">
          {filtered.map((skill) => (
            <button
              key={skill.id}
              type="button"
              onClick={() => onSelect({ ...skill, example: skill.example.trim() })}
              className="group flex h-full cursor-pointer flex-col items-start gap-3 rounded-[20px] border border-[#E5E5E5] bg-[radial-gradient(60%_60%_at_100%_100%,_#E1EAFF_0%,_#FFFFFF_100%)] p-4 text-left transition-all duration-300 hover:border-slate-200 hover:shadow-md active:scale-[1.02] md:p-5"
            >
              <div className="flex items-center gap-2">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full border-[#2563EB] bg-[#2563EB]/15 text-blue-600">
                  <FileTextIcon />
                </div>
                <span className="text-sm font-normal text-black md:text-base">{skill.name}</span>
              </div>
              <p className="line-clamp-2 text-xs leading-relaxed break-all text-[#666666] transition-colors md:text-sm">
                {skill.description}
              </p>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
