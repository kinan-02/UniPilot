import { Menu, PanelRightOpen, Sparkles } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { AgentChatHeader, AgentEmptyState, AgentMessageTimeline } from '../components/agent/AgentChatArea'
import { AgentComposer } from '../components/agent/AgentComposer'
import { AgentContextPanel } from '../components/agent/AgentContextPanel'
import { AgentSidebar } from '../components/agent/AgentSidebar'
import { useAgentMotionEnabled } from '../components/agent/agentMotion'
import { Button } from '../components/ui/Button'
import { useAgentChat, useAgentConversations } from '../hooks/useAgentChat'
import { useTranslation } from '../i18n'
import { catalogApi, profileApi } from '../api/endpoints'
import { cn } from '../lib/utils'

export function AgentPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const conversationId = searchParams.get('c')
  const motionEnabled = useAgentMotionEnabled()

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [contextCollapsed, setContextCollapsed] = useState(false)
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)
  const [composerDraft, setComposerDraft] = useState('')
  const [composerVersion, setComposerVersion] = useState(0)

  const { conversations, createConversation, isCreating } = useAgentConversations()
  const {
    messages,
    liveTurn,
    isStreaming,
    suggestedPrompts,
    pendingActions,
    sendMessage,
    stopStreaming,
    confirmAction,
    rejectAction,
    clearLiveTurn,
    refetch,
  } = useAgentChat(conversationId)

  const profileQuery = useQuery({
    queryKey: ['student-profile'],
    queryFn: () => profileApi.get(),
  })

  const profile = profileQuery.data?.profile
  const programQuery = useQuery({
    queryKey: ['agent-degree-program', profile?.degreeId],
    queryFn: async () => {
      if (!profile?.degreeId) return null
      const programs = await catalogApi.degreePrograms()
      return programs.items.find((item) => item.id === profile.degreeId) ?? null
    },
    enabled: Boolean(profile?.degreeId),
  })

  useEffect(() => {
    if (conversationId || isCreating) return
    if (conversations.length > 0) {
      setSearchParams({ c: conversations[0].id }, { replace: true })
      return
    }
    void createConversation().then((result) => {
      setSearchParams({ c: result.conversation.id }, { replace: true })
    })
  }, [conversationId, conversations, createConversation, isCreating, setSearchParams])

  useEffect(() => {
    if (liveTurn && (liveTurn.status === 'completed' || liveTurn.status === 'failed')) {
      const timer = window.setTimeout(() => {
        void refetch()
        clearLiveTurn()
      }, 400)
      return () => window.clearTimeout(timer)
    }
  }, [clearLiveTurn, liveTurn, refetch])

  const profileLabel = useMemo(() => {
    if (!profile) return null
    const parts = [
      programQuery.data?.name ?? programQuery.data?.nameEn,
      profile.academicPath?.trackSlug,
      profile.catalogYear ? `${t('agent.catalogYearShort')} ${profile.catalogYear}` : null,
    ].filter(Boolean)
    return parts.length ? parts.join(' · ') : null
  }, [profile, programQuery.data, t])

  const profileWarning = !profile?.degreeId || !profile.catalogYear
  const latestBlocks = useMemo(() => {
    if (liveTurn?.blocks.length) return liveTurn.blocks
    const lastAssistant = [...messages].reverse().find((item) => item.kind === 'assistant')
    return lastAssistant?.kind === 'assistant' ? lastAssistant.blocks : []
  }, [liveTurn?.blocks, messages])

  const ensureConversationId = async (): Promise<string | null> => {
    if (conversationId) return conversationId
    const created = await createConversation()
    setSearchParams({ c: created.conversation.id })
    return created.conversation.id
  }

  const handleNewChat = async () => {
    const result = await createConversation()
    setSearchParams({ c: result.conversation.id })
    setMobileSidebarOpen(false)
    setComposerDraft('')
  }

  const handleSelectConversation = (id: string) => {
    setSearchParams({ c: id })
    setMobileSidebarOpen(false)
  }

  const handleSend = async (content: string, attachments?: File[]) => {
    const activeId = conversationId ?? (await ensureConversationId())
    if (!activeId) return
    if (!conversationId) {
      setSearchParams({ c: activeId })
    }
    await sendMessage(content, attachments, activeId)
    setComposerDraft('')
  }

  const handleInsertPrompt = (prompt: string) => {
    setComposerDraft(prompt)
    setComposerVersion((value) => value + 1)
  }

  const handleSelectPrompt = (prompt: string) => {
    void handleSend(prompt)
  }

  const showEmpty = messages.length === 0 && !liveTurn && !isStreaming

  return (
    <div className="agent-mesh-bg flex h-screen flex-col" data-testid="agent-page">
      <div className="flex min-h-0 flex-1">
        <AnimatePresence>
          {mobileSidebarOpen ? (
            <motion.button
              key="sidebar-overlay"
              type="button"
              className="fixed inset-0 z-30 bg-[var(--color-text)]/20 backdrop-blur-[2px] lg:hidden"
              onClick={() => setMobileSidebarOpen(false)}
              aria-label={t('agent.closeSidebar')}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
            />
          ) : null}
        </AnimatePresence>

        <div
          className={cn(
            'fixed inset-y-0 start-0 z-40 lg:static lg:z-auto',
            'transition-transform duration-300 ease-out lg:translate-x-0',
            mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
          )}
        >
          <AgentSidebar
            conversations={conversations}
            activeId={conversationId}
            collapsed={sidebarCollapsed}
            onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
            onSelect={handleSelectConversation}
            onNewChat={handleNewChat}
            isCreating={isCreating}
          />
        </div>

        <main className="relative flex min-w-0 flex-1 flex-col">
          <div className="flex items-center gap-2 border-b border-[var(--color-border)]/80 agent-glass px-4 py-3 lg:hidden">
            <Button variant="ghost" size="sm" onClick={() => setMobileSidebarOpen(true)}>
              <Menu className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <p className="text-sm font-semibold tracking-tight">{t('agent.title')}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="ms-auto"
              onClick={() => setContextCollapsed(false)}
            >
              <PanelRightOpen className="h-4 w-4" />
            </Button>
          </div>

          <AgentChatHeader profileLabel={profileLabel} profileWarning={profileWarning} />

          <div className="min-h-0 flex-1 overflow-y-auto scroll-smooth">
            <AnimatePresence mode="wait">
              {showEmpty ? (
                <motion.div
                  key="empty"
                  initial={motionEnabled ? { opacity: 0 } : false}
                  animate={{ opacity: 1 }}
                  exit={motionEnabled ? { opacity: 0 } : undefined}
                  transition={{ duration: 0.25 }}
                  className="h-full"
                >
                  <AgentEmptyState onSelectPrompt={handleInsertPrompt} />
                </motion.div>
              ) : (
                <motion.div
                  key={conversationId ?? 'chat'}
                  initial={motionEnabled ? { opacity: 0, y: 8 } : false}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
                >
                  <AgentMessageTimeline
                    messages={messages}
                    liveTurn={liveTurn}
                    suggestedPrompts={suggestedPrompts}
                    isStreaming={isStreaming}
                    onSelectPrompt={handleSelectPrompt}
                    onConfirmAction={(actionId) => confirmAction.mutate(actionId)}
                    onRejectAction={(actionId) => rejectAction.mutate(actionId)}
                    isConfirming={confirmAction.isPending}
                  />
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          <div className="relative z-10 px-4 pb-4 pt-2">
            <div className="pointer-events-none absolute inset-x-0 -top-8 h-8 bg-gradient-to-t from-[var(--color-surface-muted)] to-transparent" />
            <AgentComposer
              key={composerVersion}
              initialValue={composerDraft}
              onSend={handleSend}
              onStop={stopStreaming}
              disabled={isCreating}
              isStreaming={isStreaming}
            />
          </div>
        </main>

        <AgentContextPanel
          profile={profile}
          programName={programQuery.data?.name ?? programQuery.data?.nameEn ?? null}
          blocks={latestBlocks}
          pendingActions={pendingActions}
          collapsed={contextCollapsed}
          onToggleCollapsed={() => setContextCollapsed((value) => !value)}
          onConfirmAction={(actionId) => confirmAction.mutate(actionId)}
          onRejectAction={(actionId) => rejectAction.mutate(actionId)}
          isConfirming={confirmAction.isPending}
        />
      </div>

      <div className="border-t border-[var(--color-border)]/80 agent-glass px-4 py-2 lg:hidden">
        <button
          type="button"
          className="text-xs text-[var(--color-text-muted)] transition hover:text-[var(--color-primary)]"
          onClick={() => navigate('/')}
        >
          {t('agent.backToApp')}
        </button>
      </div>
    </div>
  )
}
