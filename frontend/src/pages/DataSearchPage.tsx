import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Database, type DatabaseSearchResponse } from '../api/client'

function ResultView({ data }: { data: DatabaseSearchResponse }) {
  if (data.error) {
    return <p className="text-sm text-red-600">{data.error}</p>
  }
  if (data.message) {
    return <p className="text-sm text-slate-600">{data.message}</p>
  }
  if (!data.result) return null

  const r = data.result as Record<string, unknown>
  const count = r.count as number | undefined

  return (
    <div className="space-y-4 text-sm">
      {typeof count === 'number' && (
        <p className="font-medium text-slate-700">共 {count} 条结果</p>
      )}

      {Array.isArray(r.hits) && r.hits.length > 0 && (
        <div className="space-y-2">
          {(r.hits as Record<string, unknown>[]).map((hit, i) => (
            <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="font-medium text-slate-900">{String(hit.name ?? hit.id ?? '')}</div>
              {hit.id != null && <div className="text-xs text-slate-500">ID: {String(hit.id)}</div>}
              {hit.description != null && (
                <div className="mt-1 text-slate-600">{String(hit.description)}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {Array.isArray(r.compounds) && r.compounds.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-xs">
            <thead>
              <tr className="border-b text-slate-500">
                <th className="py-2 pr-3">ChEMBL ID</th>
                <th className="py-2 pr-3">名称</th>
                <th className="py-2 pr-3">类型</th>
                <th className="py-2 pr-3">pChEMBL</th>
                <th className="py-2">SMILES</th>
              </tr>
            </thead>
            <tbody>
              {(r.compounds as Record<string, unknown>[]).map((c, i) => (
                <tr key={i} className="border-b border-slate-100">
                  <td className="py-2 pr-3 font-mono">{String(c.chembl_id ?? '')}</td>
                  <td className="py-2 pr-3">{String(c.pref_name ?? '')}</td>
                  <td className="py-2 pr-3">{String(c.standard_type ?? '')}</td>
                  <td className="py-2 pr-3">{String(c.pchembl_value ?? '')}</td>
                  <td className="max-w-[200px] truncate py-2 font-mono text-[11px]">
                    {String(c.canonical_smiles ?? '')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {Array.isArray(r.matches) && r.matches.length > 0 && (
        <div className="space-y-2">
          {(r.matches as Record<string, unknown>[]).map((m, i) => (
            <div key={i} className="rounded-lg border border-slate-200 bg-white px-3 py-2">
              <span className="font-medium">{String(m.zh)}</span>
              <span className="mx-2 text-slate-400">→</span>
              <span className="text-[#2563EB]">{String(m.en)}</span>
            </div>
          ))}
        </div>
      )}

      {Array.isArray(r.drugs) && r.drugs.length > 0 && (
        <div className="space-y-2">
          {(r.drugs as Record<string, unknown>[]).slice(0, 10).map((d, i) => (
            <div key={i} className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="font-medium">{String(d.name ?? '')}</div>
              <div className="mt-1 truncate font-mono text-xs text-slate-500">{String(d.smiles ?? '')}</div>
            </div>
          ))}
        </div>
      )}

      {Array.isArray(r.mappings) && r.mappings.length > 0 && (
        <div className="space-y-1 font-mono text-xs">
          {(r.mappings as Record<string, unknown>[]).map((m, i) => (
            <div key={i}>
              {String(m.chembl_id)} ↔ {String(m.uniprot_id)}
            </div>
          ))}
        </div>
      )}

      {r.download_url != null && (
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="font-medium">PDB: {String(r.query)}</div>
          <div className="mt-1 text-xs text-slate-500">
            可访问: {r.reachable ? '是' : '否'}
          </div>
          <a
            href={String(r.download_url)}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-block text-[#2563EB] hover:underline"
          >
            下载结构文件
          </a>
          {r.thumbnail_url != null && (
            <img
              src={String(r.thumbnail_url)}
              alt={`PDB ${String(r.query)}`}
              className="mt-3 max-h-40 rounded border"
            />
          )}
        </div>
      )}

      {r.preview != null && (
        <pre className="overflow-x-auto rounded-lg border bg-slate-50 p-3 text-xs">
          {String(r.preview)}
        </pre>
      )}

      <details className="text-xs text-slate-500">
        <summary className="cursor-pointer">原始 JSON</summary>
        <pre className="mt-2 overflow-x-auto rounded bg-slate-50 p-2">{JSON.stringify(r, null, 2)}</pre>
      </details>
    </div>
  )
}

export default function DataSearchPage() {
  const { databaseId } = useParams<{ databaseId: string }>()
  const navigate = useNavigate()
  const [db, setDb] = useState<Database | null>(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<DatabaseSearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!databaseId) return
    api
      .getDatabase(databaseId)
      .then((d) => {
        setDb(d)
        setQuery(d.example_query)
      })
      .catch((e) => setError(e instanceof Error ? e.message : '加载失败'))
  }, [databaseId])

  const handleSearch = async () => {
    if (!databaseId || !query.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.searchDatabase(databaseId, query.trim())
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : '查询失败')
    } finally {
      setLoading(false)
    }
  }

  const handleAskAgent = () => {
    if (!db) return
    const prompt =
      result?.chat_prompt ??
      `请使用【${db.name}】数据源查询以下信息：${query.trim()}`
    navigate('/', { state: { prompt } })
  }

  if (!db && !error) {
    return (
      <div className="flex flex-1 items-center justify-center text-slate-500">加载中...</div>
    )
  }

  if (error && !db) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3">
        <p className="text-red-600">{error}</p>
        <button
          type="button"
          onClick={() => navigate('/data')}
          className="text-sm text-[#2563EB] hover:underline"
        >
          返回数据广场
        </button>
      </div>
    )
  }

  if (!db) return null

  return (
    <div className="flex-1 overflow-y-auto">
      <main className="mx-auto w-full max-w-3xl px-3 py-6 pb-16 md:px-8 md:py-10">
        <button
          type="button"
          onClick={() => navigate('/data')}
          className="mb-4 text-sm text-[#2563EB] hover:underline"
        >
          ← 返回数据广场
        </button>

        <div className="mb-6 rounded-[20px] border border-[#E5E5E5] bg-white p-5 md:p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{db.icon}</span>
            <div>
              <h1 className="text-xl font-extrabold text-slate-900">{db.name}</h1>
              <p className="text-xs text-slate-500">{db.category}</p>
            </div>
          </div>
          <p className="mt-4 text-sm leading-relaxed text-[#666666]">{db.description}</p>
          <p className="mt-2 text-xs text-slate-500">
            <span className="font-medium text-slate-600">所属：</span>
            <span className="font-semibold text-slate-800">{db.project || '药物研发'}</span>
            <span className="mx-2 text-slate-300">·</span>
            <span className="font-medium text-slate-600">数据量：</span>
            <span className="font-bold text-slate-900">{db.volume}</span>
          </p>
        </div>

        <div className="rounded-[20px] border border-[#E5E5E5] bg-[radial-gradient(60%_60%_at_100%_100%,_#E1EAFF_0%,_#FFFFFF_100%)] p-5 md:p-6">
          <label htmlFor="data-query" className="mb-2 block text-sm font-semibold text-slate-800">
            检索内容
          </label>
          <input
            id="data-query"
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder={db.example_query}
            className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none focus:border-[#2563EB] focus:ring-2 focus:ring-[#2563EB]/20"
          />
          <p className="mt-2 text-xs text-slate-400">示例：{db.example_query}</p>

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleSearch}
              disabled={loading || !query.trim()}
              className="rounded-xl bg-[#2563EB] px-5 py-2.5 text-sm font-medium text-white transition hover:bg-[#1d4ed8] disabled:opacity-50"
            >
              {loading ? '查询中...' : '查询'}
            </button>
            <button
              type="button"
              onClick={handleAskAgent}
              className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
            >
              交给智能体分析
            </button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
          <div className="mt-6 rounded-[20px] border border-slate-200 bg-white p-5 md:p-6">
            <h2 className="mb-4 text-base font-bold text-slate-900">查询结果</h2>
            <ResultView data={result} />
            {!result.searchable && result.chat_prompt && (
              <button
                type="button"
                onClick={handleAskAgent}
                className="mt-4 text-sm font-medium text-[#2563EB] hover:underline"
              >
                通过智能体查询 →
              </button>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
