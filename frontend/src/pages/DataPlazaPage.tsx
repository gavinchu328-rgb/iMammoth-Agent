import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api, type Database } from '../api/client'
import { dataPlazaPath } from '../utils/dataPlaza'

export default function DataPlazaPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [databases, setDatabases] = useState<Database[]>([])

  useEffect(() => {
    api.databases().then(setDatabases).catch(console.error)
  }, [])

  const projects = useMemo(
    () => ['全部', ...Array.from(new Set(databases.map((d) => d.project || '药物研发')))],
    [databases],
  )

  const projectParam = searchParams.get('project')
  const categoryParam = searchParams.get('category')
  const project =
    projectParam && projects.includes(projectParam) ? projectParam : '全部'

  const byProject =
    project === '全部' ? databases : databases.filter((d) => (d.project || '药物研发') === project)

  const categories = useMemo(
    () => ['全部', ...Array.from(new Set(byProject.map((d) => d.category)))],
    [byProject],
  )

  const active =
    categoryParam && categories.includes(categoryParam) ? categoryParam : '全部'

  const filtered = active === '全部' ? byProject : byProject.filter((d) => d.category === active)

  const setProject = (p: string) => {
    const next = new URLSearchParams(searchParams)
    if (p === '全部') next.delete('project')
    else next.set('project', p)
    next.delete('category')
    setSearchParams(next, { replace: true })
  }

  const setActive = (cat: string) => {
    const next = new URLSearchParams(searchParams)
    if (cat === '全部') next.delete('category')
    else next.set('category', cat)
    setSearchParams(next, { replace: true })
  }

  return (
    <div className="flex-1 overflow-y-auto">
      <main className="mx-auto w-full max-w-7xl px-3 py-6 pb-16 md:px-8 md:py-10">
        <div className="mb-6">
          <h1 className="text-xl font-extrabold text-slate-900 md:text-2xl">数据广场</h1>
          <p className="mt-1 text-sm text-[#666666]">
            药物研发与物质科学用到的数据源，点击卡片进入检索
          </p>
        </div>

        <div className="mb-3 flex min-w-max flex-nowrap justify-start gap-2 overflow-x-auto md:flex-wrap md:gap-3">
          {projects.map((p) => {
            const isActive = project === p
            return (
              <button
                key={p}
                type="button"
                onClick={() => {
                  setProject(p)
                }}
                className={`rounded-full px-3 py-1.5 text-sm transition select-none ${
                  isActive
                    ? 'bg-[#2563EB] font-bold text-white'
                    : 'bg-slate-100 font-medium text-[#666666] hover:bg-slate-200'
                }`}
              >
                {p}
              </button>
            )
          })}
        </div>

        <div className="mb-4 flex min-w-max flex-nowrap justify-start gap-2 overflow-x-auto md:flex-wrap md:justify-start md:gap-3">
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

        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 md:gap-3 lg:grid-cols-3">
          {filtered.map((db) => (
            <button
              key={db.id}
              type="button"
              onClick={() =>
                navigate(`/data/${db.id}`, {
                  state: { returnTo: dataPlazaPath(project, active) },
                })
              }
              className="group flex h-full cursor-pointer flex-col items-start gap-3 rounded-[20px] border border-[#E5E5E5] bg-[radial-gradient(60%_60%_at_100%_100%,_#E1EAFF_0%,_#FFFFFF_100%)] p-4 text-left transition-all duration-300 hover:border-slate-200 hover:shadow-md active:scale-[1.02] md:p-5"
            >
              <div className="flex items-center gap-2">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full border-[#2563EB] bg-[#2563EB]/15 text-base">
                  {db.icon}
                </div>
                <span className="truncate text-sm font-semibold text-black md:text-base">{db.name}</span>
              </div>

              <p className="line-clamp-3 text-xs leading-relaxed text-[#666666] md:text-sm">{db.description}</p>

              <div className="mt-auto w-full space-y-1 border-t border-slate-100 pt-2 text-xs text-slate-500">
                <div>
                  <span className="font-medium text-slate-600">数据量：</span>
                  <span className="font-bold text-slate-900">{db.volume}</span>
                </div>
                {db.searchable && (
                  <div className="font-medium text-[#2563EB]">支持直接检索 →</div>
                )}
              </div>
            </button>
          ))}
        </div>
      </main>
    </div>
  )
}
