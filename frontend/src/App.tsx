import { useRef, useState, useCallback } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import BackendStatusBanner from './components/BackendStatusBanner'
import ChatPage, { type ChatPageHandle } from './pages/ChatPage'
import SkillsPage from './pages/SkillsPage'
import AgentsPage from './pages/AgentsPage'
import AgentDetailPage from './pages/AgentDetailPage'
import DataPlazaPage from './pages/DataPlazaPage'
import DataSearchPage from './pages/DataSearchPage'
import { useSessions } from './hooks/useChat'
import { useBackendHealth } from './hooks/useBackendHealth'
import { ChatProvider } from './context/ChatContext'

export default function App() {
  const chatRef = useRef<ChatPageHandle>(null)
  const navigate = useNavigate()
  const { sessions, refresh, remove, loadStatus: sessionsLoadStatus } = useSessions()
  const { health: backendHealth } = useBackendHealth()
  const [collapsed, setCollapsed] = useState(false)
  const [currentSessionId, setCurrentSessionId] = useState<string>()

  const handleNewChat = useCallback(() => {
    chatRef.current?.newChat()
    setCurrentSessionId(undefined)
    navigate('/')
  }, [navigate])

  const handleSelectSession = useCallback(
    (id: string) => {
      setCurrentSessionId(id)
      navigate(`/c/${id}`)
    },
    [navigate],
  )

  const handleDeleteSession = useCallback(
    async (id: string) => {
      try {
        await remove(id)
        if (currentSessionId === id) {
          chatRef.current?.newChat()
          setCurrentSessionId(undefined)
          navigate('/')
        }
      } catch (e) {
        console.error(e)
        window.alert(e instanceof Error ? e.message : '删除失败')
      }
    },
    [remove, currentSessionId, navigate],
  )

  const handleSessionChange = useCallback(
    (sessionId?: string) => {
      setCurrentSessionId(sessionId)
      refresh().catch(console.error)
    },
    [refresh],
  )

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <BackendStatusBanner health={backendHealth} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          sessions={sessions}
          sessionsLoadStatus={sessionsLoadStatus}
          currentSessionId={currentSessionId}
          onNewChat={handleNewChat}
          onSelectSession={handleSelectSession}
          onDeleteSession={handleDeleteSession}
          collapsed={collapsed}
          onToggle={() => setCollapsed((v) => !v)}
        />
        <main className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-[#F9FAFB]">
          <ChatProvider>
            <Routes>
              <Route
                path="/"
                element={<ChatPage ref={chatRef} onSessionChange={handleSessionChange} />}
              />
              <Route
                path="/c/:sessionId"
                element={<ChatPage ref={chatRef} onSessionChange={handleSessionChange} />}
              />
              <Route path="/skills" element={<SkillsPage />} />
              <Route path="/data" element={<DataPlazaPage />} />
              <Route path="/data/:databaseId" element={<DataSearchPage />} />
              <Route path="/agents" element={<AgentsPage />} />
              <Route path="/agents/:agentId" element={<AgentDetailPage />} />
            </Routes>
          </ChatProvider>
        </main>
      </div>
    </div>
  )
}
