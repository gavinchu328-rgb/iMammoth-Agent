import { useMemo, useState } from 'react'
import {
  extractPdbIds,
  pdb3dViewUrl,
  pdbDownloadUrl,
  pdbRcsbPageUrl,
  pdbThumbnailUrl,
} from '../utils/processStepUtils'

interface Props {
  pdbIds: string[]
  compact?: boolean
}

export default function PdbStructureCards({ pdbIds, compact = false }: Props) {
  const ids = useMemo(() => pdbIds.slice(0, compact ? 4 : 8), [pdbIds, compact])
  const [broken, setBroken] = useState<Record<string, boolean>>({})

  if (ids.length === 0) return null

  return (
    <div className={`mt-2 flex flex-wrap gap-2 ${compact ? '' : 'gap-3'}`}>
      {ids.map((id) => (
        <div
          key={id}
          className={`overflow-hidden rounded-lg border border-slate-200 bg-white ${
            compact ? 'w-[140px]' : 'w-[168px]'
          }`}
        >
          <div className="relative aspect-[4/3] bg-slate-100">
            {!broken[id] ? (
              <img
                src={pdbThumbnailUrl(id)}
                alt={`PDB ${id}`}
                className="h-full w-full object-cover"
                loading="lazy"
                onError={() => setBroken((prev) => ({ ...prev, [id]: true }))}
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs font-semibold text-slate-500">
                {id}
              </div>
            )}
          </div>
          <div className="space-y-1 px-2 py-1.5 text-[11px]">
            <div className="font-semibold text-slate-800">PDB {id}</div>
            <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-[#2563EB]">
              <a href={pdbRcsbPageUrl(id)} target="_blank" rel="noopener noreferrer">
                RCSB
              </a>
              <a href={pdbDownloadUrl(id)} target="_blank" rel="noopener noreferrer">
                下载
              </a>
              <a href={pdb3dViewUrl(id)} target="_blank" rel="noopener noreferrer">
                3D 预览
              </a>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

interface StepProps {
  title?: string
  name?: string
  input?: string
  result?: string
  detail?: string
}

export function PdbCardsFromStepText({ title, name, input, result, detail }: StepProps) {
  const ids = useMemo(
    () => extractPdbIds(title, name, input, result, detail),
    [title, name, input, result, detail],
  )
  return <PdbStructureCards pdbIds={ids} compact />
}
