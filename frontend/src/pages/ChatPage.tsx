import { useEffect, useState, useImperativeHandle, forwardRef, useRef, useCallback } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api, type Skill } from '../api/client'
import { useChatContext } from '../context/ChatContext'
import { useApiRetry } from '../hooks/useApiRetry'
import WelcomeHeader from '../components/WelcomeHeader'
import SkillPlaza from '../components/SkillPlaza'
import MessageList from '../components/MessageList'
import ChatInput from '../components/ChatInput'

type LocationState = { prompt?: string; skill?: Skill }

function buildSkillSystemPrompt(skill: Skill) {
  const lines = [
    `本轮对话请优先匹配并调用与「${skill.name}」对应的技能/工具。`,
    `技能分类：${skill.category}。`,
    `技能说明：${skill.description}。`,
    `优先按这个技能的能力范围来理解用户问题；如果存在对应的 OpenClaw skill、MCP 工具或内置工具，请先调用它，而不是直接凭记忆作答。`,
    `如果该技能能够产生结构化结果，请先拿到结果再组织中文回答。`,
  ]
  if (skill.name === '分子设计') {
    lines.push(
      '本技能仅生成候选小分子。若 session 尚无口袋：先 protein_acquisition（target_ids 如 EGFR_1M14）+ pocket_prediction。',
      'molecule_design 的 pocket_ids 必须使用 pocket_prediction 返回的完整 pocket_id（如 EGFR_1M14_pocket1），禁止只传 pocket1。',
      'num_to_generate 设为用户要求的数量（通常 5~8）；只调用一次 molecule_design。',
      '所有 mcporter 调用必须加 --timeout 600000（毫秒，即 10 分钟；勿写成 600）；必须同步等待工具完整返回 molecules[]；禁止后台 process 轮询。',
      '用户已指定靶点/口袋时，禁止调用靶点发现；禁止受体准备、对接盒、分子对接、ADMET。',
    )
  }
  if (skill.name === '对接盒配置') {
    lines.push(
      '本技能仅配置对接搜索盒，禁止靶点发现、受体准备、配体准备、分子对接。',
      'session_id 必须用当前猛犸 UUID；pocket_ids 用完整 pocket_id（如 EGFR_3W2S_pocket1）。',
      '用户写了 pocket_id 只表示目标口袋名称，不等于本会话已有口袋数据。',
      '本对话尚未执行 pocket_prediction 时：先 protein_acquisition(从 pocket_id 推断 EGFR_3W2S) → pocket_prediction → docking_box_config；不要先调 docking_box_config 等失败。',
      '必须通过 exec 调用 mcporter 执行工具，禁止仅凭记忆编造 ## 分析过程 或跳过工具调用。',
      '最终回答用表格+报告链接即可；禁止输出「完整结构化数据」或 ```json 工具原始返回。',
      '用户已给 EGFR/3W2S/pocket_id 时禁止追问；所有 mcporter --timeout 600000；禁止 sessions_spawn。',
    )
  }
  if (skill.name === '分子对接') {
    lines.push(
      '本技能执行 Vina 分子对接。全程使用同一猛犸 session_id；conformer_generation 必须传 session_id，否则会话隔离导致失败。',
      '流程：protein_acquisition → receptor_preparation → pocket_prediction → docking_box_config → conformer_generation → ligand_preparation → molecular_docking。',
      'target_ids 格式 EGFR_3W2S；pocket_ids / molecule_ids 必须用完整 pocket_id（如 EGFR_3W2S_pocket1）。',
      'conformer_generation 的 molecules[].id 必须为 `{pocket_id}_mol0`（如 EGFR_3W2S_pocket1_mol0），禁止用 gefitinib 等药物名。',
      'ligand_preparation 与 molecular_docking 的 molecule_ids 必须与构象 id 完全一致。',
      '吉非替尼 SMILES：CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl。禁止靶点发现；对接成功前禁止 pipeline_summary。',
      '最终回答用表格+报告链接即可；禁止输出「完整结构化数据」或 ```json 工具原始返回。',
    )
  }
  if (skill.name === '配体准备') {
    lines.push(
      '本技能仅生成 PDBQT 配体，标准流程两步：conformer_generation → ligand_preparation。',
      'session_id 必须用当前猛犸 UUID，禁止用 target_discovery 返回的 session_id。',
      'molecules[].id 必须为 `{pocket_id}_mol0`（如 EGFR_3W2S_pocket1_mol0），ligand_preparation 的 molecule_ids 与之完全一致。',
      '用户已给 SMILES 与 pocket_id / molecule id 时：只执行上述两步；禁止靶点发现、禁止 web_search、禁止受体准备/对接盒/分子对接。',
      '用户只给药物名时：吉非替尼 SMILES 用 CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl；未给 pocket 默认 EGFR_3W2S_pocket1_mol0。',
      '仅当 session 确认无口袋时才补 protein_acquisition + pocket_prediction。所有 mcporter 加 --timeout 600000；禁止 sessions_spawn。',
      '最终回答用表格+报告链接即可；禁止输出「完整结构化数据」或 ```json 工具原始返回。',
    )
  }
  if (skill.name === '受体准备') {
    lines.push(
      '先 protein_acquisition（target_ids 如 EGFR_3W2S），再 receptor_preparation（target_ids 同上）。禁止 sessions_spawn。',
    )
  }
  if (skill.name === '3D构象生成') {
    lines.push(
      '调用 conformer_generation，必须传猛犸 session_id；molecules[].id 可用简短 id（如 aspirin）。禁止 sessions_spawn。',
    )
  }
  if (skill.name === 'ADMET评估') {
    lines.push(
      '本技能仅两步：conformer_generation → molecule_evaluation；禁止靶点发现、分子对接、联网查 SMILES。',
      'session_id 必须用当前猛犸 UUID（两步同一 UUID，禁止用 conformer 返回的时间戳 session）；用户已给 SMILES 时禁止 web_search/web_fetch/tavily，不要编造 SMILES。',
      '吉非替尼 SMILES：CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl，id=gefitinib_mol0。',
      'conformer 必须显式传 session_id（建议 mcporter --args-file）；构象已生成则禁止因响应 session_id 不同而重试。',
      'molecule_evaluation 的 molecule_ids 与构象 id 一致；禁止输出完整结构化数据/尾随 JSON。',
      '禁止 sessions_spawn；所有 mcporter --timeout 600000；等工具完整返回后再总结。',
    )
  }
  if (skill.name === '逆合成分析') {
    lines.push(
      '本技能仅两步：conformer_generation → retrosynthesis；禁止靶点发现、分子对接、联网查 SMILES。',
      'session_id 必须用当前猛犸 UUID（两步同一 UUID，禁止用 conformer 返回的时间戳 session）；用户已给 SMILES 时禁止 web_search/web_fetch/tavily，不要编造 SMILES。',
      '吉非替尼 SMILES：CN1CCN(CC1)COc2ccc3nc(ncc3c2)Cl，id=gefitinib_mol0；禁止声称该 SMILES 与吉非替尼不符。',
      'conformer 的 method/num_conformers 等放在 params 对象内；复杂参数用 mcporter --args-file 传 JSON；retrosynthesis 的 molecule_ids 与构象 id 一致。',
      '若 retrosynthesis 返回 no synthesis routes found，如实报告未找到路线，禁止编造参考合成或文献工艺。',
      '禁止 sessions_spawn；所有 mcporter --timeout 600000；等工具完整返回后再总结，禁止未完成就结束。',
    )
  }
  if (skill.name === '靶点发现') {
    lines.push(
      '通过 exec 调用 mcporter call ai4drug.target_discovery，必须显式加 --timeout 600000（毫秒，10 分钟）。',
      '传入 disease_name 与当前猛犸 session_id；禁止 sessions_spawn、禁止后台 process 轮询。',
      '一次调用同步等待返回即可。',
    )
  }
  if (skill.name === '蛋白质获取') {
    lines.push(
      'mcporter call ai4drug.protein_acquisition 必须加 --timeout 600000；target_ids 格式基因_PDB（如 EGFR_3W2S）。',
      '传猛犸 session_id；禁止 sessions_spawn。',
    )
  }
  if (skill.name === '口袋预测') {
    lines.push(
      '流程：protein_acquisition（EGFR_3W2S，--timeout 600000）→ pocket_prediction（同一 session_id，--timeout 600000）。',
      '禁止 sessions_spawn。最终回答必须用表格列出 pocket_id、评分、概率（按评分降序）。',
    )
  }
  if (skill.name === '化学智能中心') {
    lines.push(
      '调用 huaxue :3010 的 curl 必须前台同步等待返回（--max-time 180 足够），禁止 process 后台轮询。',
      '反应预测用 POST /api/ai/reaction-predict；逆合成用 POST /api/ai/retrosynthesis。',
      '两个任务顺序执行即可；工具返回后再写最终回答。',
    )
  }
  if (skill.id === 'pdb-text-search') {
    lines.push(
      '禁止 read database-lookup、禁止 sessions_spawn、禁止凭记忆编造 PDB 结果。',
      '禁止 curl data.rcsb.org、search.rcsb.org 或任何手写 RCSB 脚本。',
      '必须且仅通过 exec 调用猛犸内置接口（只调用一次，不要重复搜索）：',
      "curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb-text/search -H 'Content-Type: application/json' -d '{\"query\":\"<关键词>\"}'",
      '结果已按分辨率从高到低排序；解析 total_count 与 hits[].pdb_id、hits[].resolution，直接列出前 10 条即可回答「高分辨率」问题。',
      '分析步骤标题写「PDB 文本搜索」。若用户还要标题/实验方法，再对每个 PDB ID 调用元数据接口，不要手写 RCSB curl。',
    )
  }
  if (skill.id === 'pdb-metadata-lookup') {
    lines.push(
      '禁止 read database-lookup、禁止 sessions_spawn、禁止凭记忆编造元数据。',
      '禁止 curl data.rcsb.org、search.rcsb.org；query 必须是 4 位 PDB ID（如 4Z9H），不要用 entity id。',
      '必须且仅通过 exec 调用猛犸内置接口（只调用一次）：',
      "curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb-metadata/search -H 'Content-Type: application/json' -d '{\"query\":\"<PDB_ID>\"}'",
      '解析 resolution、experimental_method、title、release_date、ligands[]（含 chem_comp_id 与配体名称）；步骤标题写「PDB 元数据查询」。',
      '禁止为配体 entity 再单独调接口；配体信息已在 ligands 字段中。',
    )
  }
  if (skill.id === 'pdb-structure-download') {
    lines.push(
      '禁止 read database-lookup、禁止 sessions_spawn。',
      '必须且仅通过 exec 调用猛犸内置接口（一次即可）：',
      "curl -sS -X POST http://127.0.0.1:8080/api/databases/rcsb-pdb/search -H 'Content-Type: application/json' -d '{\"query\":\"<PDB_ID>\"}'",
      '返回 download_url、thumbnail_url、reachable；步骤标题写「PDB 结构下载」。',
      '3D 预览请给出 RCSB 官方链接：https://www.rcsb.org/3d-view/<PDB_ID>。',
    )
  }
  return lines.join('\n')
}

export interface ChatPageHandle {
  newChat: () => void
  loadSession: (id: string) => void
  setPrompt: (text: string) => void
}

interface Props {
  onSessionChange?: (sessionId?: string) => void
}

const ChatPage = forwardRef<ChatPageHandle, Props>(function ChatPage({ onSessionChange }, ref) {
  const { sessionId: routeSessionId } = useParams<{ sessionId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const { sessionId, messages, loading, streaming, error, isConversation, loadSession, sendMessage, stopGeneration, newChat } =
    useChatContext()
  const [input, setInput] = useState('')
  const [selectedSkill, setSelectedSkill] = useState<Skill | undefined>(undefined)
  const [skills, setSkills] = useState<Skill[]>([])
  const [restoring, setRestoring] = useState(Boolean(routeSessionId))
  const welcomeScrollRef = useRef<HTMLDivElement>(null)
  const composerRef = useRef<HTMLDivElement>(null)

  const scrollToComposer = () => {
    welcomeScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
    requestAnimationFrame(() => {
      composerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      composerRef.current?.querySelector('textarea')?.focus()
    })
  }

  useApiRetry(
    useCallback(async () => {
      const list = await api.skills()
      setSkills(list)
    }, []),
  )

  // 从技能广场跳转时携带 prompt + skill，填入对话框后滚到顶部并清掉 state
  useEffect(() => {
    const state = location.state as LocationState | null
    if (!state?.prompt && !state?.skill) return
    if (state.prompt) setInput(state.prompt)
    if (state.skill) setSelectedSkill(state.skill)
    navigate(location.pathname, { replace: true, state: {} })
    // 下一帧再滚，确保欢迎页已渲染
    requestAnimationFrame(() => scrollToComposer())
  }, [location.state, location.pathname, navigate])

  // 刷新 / 直链：从 URL 恢复会话（对齐 Matwings /chat/agent/:id）
  useEffect(() => {
    if (!routeSessionId) {
      setRestoring(false)
      return
    }
    // 刚结束流式对话时 URL 从 / 跳到 /c/:id，本地已有消息则不必重新拉取
    if (sessionId === routeSessionId && messages.length > 0) {
      setRestoring(false)
      onSessionChange?.(routeSessionId)
      return
    }
    let cancelled = false
    setRestoring(true)
    ;(async () => {
      try {
        await loadSession(routeSessionId)
        if (!cancelled) onSessionChange?.(routeSessionId)
      } catch (e) {
        console.error(e)
        if (!cancelled) {
          onSessionChange?.(undefined)
          navigate('/', { replace: true })
        }
      } finally {
        if (!cancelled) {
          setRestoring(false)
          // Restored sessions don't know which skill card was chosen last.
          setSelectedSkill(undefined)
        }
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when URL session changes
  }, [routeSessionId])

  // 流式过程中拿到 session_id 后同步 URL，避免结束后再跳转触发重载
  useEffect(() => {
    if (!sessionId || routeSessionId === sessionId) return
    if (messages.length === 0) return
    navigate(`/c/${sessionId}`, { replace: true })
    onSessionChange?.(sessionId)
  }, [sessionId, routeSessionId, messages.length, navigate, onSessionChange])

  useImperativeHandle(ref, () => ({
    newChat: () => {
      newChat()
      setInput('')
      setSelectedSkill(undefined)
      setRestoring(false)
      navigate('/')
      onSessionChange?.(undefined)
    },
    loadSession: (id: string) => {
      navigate(`/c/${id}`)
    },
    setPrompt: (text: string) => {
      setInput(text)
      // If external code sets a prompt, we don't assume a specific selected skill.
      setSelectedSkill(undefined)
    },
  }))

  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return

    const skillHint = selectedSkill
      ? {
          name: selectedSkill.name,
          category: selectedSkill.category,
          systemPrompt: buildSkillSystemPrompt(selectedSkill),
        }
      : undefined

    setInput('')
    setSelectedSkill(undefined)

    const sid = await sendMessage(text, skillHint)
    if (sid) {
      onSessionChange?.(sid)
    }
  }

  const handleSkillSelect = (skill: Skill) => {
    setSelectedSkill({ ...skill, example: skill.example.trim() })
    setInput(skill.example.trim())
    // 填入示例后滚到页面顶部输入框，方便确认并发送
    scrollToComposer()
  }

  if (restoring) {
    return (
      <div className="flex h-full flex-1 items-center justify-center text-sm text-slate-400">
        加载对话中…
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {!isConversation ? (
        <div ref={welcomeScrollRef} className="flex-1 overflow-y-auto">
          <main className="mx-auto flex w-full max-w-7xl flex-col items-center px-3 pt-4 pb-16 md:px-8 md:pt-40 md:pb-20">
            <WelcomeHeader />
            <div className="h-px w-full" />
            <div ref={composerRef} className="w-full scroll-mt-4">
              <ChatInput
                variant="center"
                value={input}
                onChange={setInput}
                onSend={handleSend}
                onStop={stopGeneration}
                loading={loading}
              />
            </div>

            {error && (
              <div className="w-full max-w-5xl px-1 py-2 text-center text-sm text-red-600">{error}</div>
            )}

            <div className="mt-2 w-full">
              <SkillPlaza
                skills={skills.slice(0, 30)}
                onSelect={handleSkillSelect}
                compact
                showTitle={false}
              />
            </div>
          </main>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-none bg-white p-0 md:m-2 md:rounded-[24px]">
          <MessageList messages={messages} loading={loading} streaming={streaming} />
          {error && <div className="px-4 py-2 text-center text-sm text-red-600">{error}</div>}
          <ChatInput value={input} onChange={setInput} onSend={handleSend} onStop={stopGeneration} loading={loading} variant="footer" />
        </div>
      )}
    </div>
  )
})

export default ChatPage
