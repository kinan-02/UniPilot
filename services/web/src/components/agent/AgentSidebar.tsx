import { Link } from 'react-router-dom'
import {
  BookOpen,
  CalendarDays,
  GraduationCap,
  LayoutDashboard,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Settings,
  Sparkles,
} from 'lucide-react'
import { motion } from 'motion/react'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { useTranslation } from '../../i18n'
import type { AgentConversation } from '../../types/agent'
import { useAgentMotionEnabled } from './agentMotion'

type AgentSidebarProps = {
  conversations: AgentConversation[]
  activeId: string | null
  collapsed: boolean
  onToggleCollapsed: () => void
  onSelect: (id: string) => void
  onNewChat: () => void
  isCreating?: boolean
}

function formatRelativeTime(value?: string | null): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const SHORTCUTS = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard' as const },
  { to: '/progress', icon: GraduationCap, labelKey: 'nav.progress' as const },
  { to: '/transcript', icon: ScrollText, labelKey: 'nav.transcript' as const },
  { to: '/plans', icon: CalendarDays, labelKey: 'nav.plans' as const },
  { to: '/catalog', icon: BookOpen, labelKey: 'nav.catalog' as const },
  { to: '/profile', icon: Settings, labelKey: 'nav.profile' as const },
]

export function AgentSidebar({
  conversations,
  activeId,
  collapsed,
  onToggleCollapsed,
  onSelect,
  onNewChat,
  isCreating,
}: AgentSidebarProps) {
  const { t } = useTranslation()
  const motionEnabled = useAgentMotionEnabled()

  return (
    <aside
      className={cn(
        'flex h-full flex-col border-e border-[var(--color-border)]/80 bg-white/95 backdrop-blur-md transition-[width] duration-300 ease-out',
        collapsed ? 'w-[72px]' : 'w-[280px]',
      )}
      data-testid="agent-sidebar"
    >
      <div className="flex items-center gap-2 border-b border-[var(--color-border)]/80 px-3 py-4">
        {!collapsed ? (
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                <Sparkles className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold tracking-tight">{t('agent.title')}</p>
                <p className="truncate text-xs text-[var(--color-text-muted)]">{t('agent.subtitle')}</p>
              </div>
            </div>
          </div>
        ) : null}
        <Button variant="ghost" size="sm" onClick={onToggleCollapsed} aria-label={t('agent.toggleSidebar')}>
          {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
        </Button>
      </div>

      <div className="p-3">
        <Button
          className={cn(
            'w-full justify-start gap-2 shadow-sm transition hover:shadow-md',
            collapsed && 'px-2',
          )}
          onClick={onNewChat}
          disabled={isCreating}
          data-testid="agent-new-chat"
        >
          <MessageSquarePlus className="h-4 w-4 shrink-0" />
          {!collapsed ? t('agent.newChat') : null}
        </Button>
      </div>

      {!collapsed ? (
        <>
          <div className="px-3 pb-2">
            <p className="px-2 text-[0.65rem] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
              {t('agent.conversations')}
            </p>
          </div>
          <div className="flex-1 overflow-y-auto px-2 pb-3">
            {conversations.length === 0 ? (
              <p className="px-2 py-4 text-xs text-[var(--color-text-muted)]">{t('agent.noConversations')}</p>
            ) : (
              <ul className="space-y-0.5">
                {conversations.map((conversation) => {
                  const isActive = activeId === conversation.id
                  const inner = (
                    <>
                      {isActive ? (
                        <span className="absolute inset-y-2 start-0 w-0.5 rounded-full bg-[var(--color-primary)]" />
                      ) : null}
                      <p className="truncate text-sm font-medium">
                        {conversation.title || conversation.lastMessagePreview || t('agent.untitledConversation')}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-[var(--color-text-muted)]">
                        {conversation.lastMessagePreview || formatRelativeTime(conversation.updatedAt)}
                      </p>
                    </>
                  )
                  const className = cn(
                    'relative w-full rounded-xl px-3 py-2.5 text-start transition-all duration-200',
                    isActive
                      ? 'bg-[var(--color-primary)]/8 text-[var(--color-primary)] shadow-sm'
                      : 'text-[var(--color-text)] hover:bg-[var(--color-surface-muted)]',
                  )
                  if (motionEnabled) {
                    return (
                      <li key={conversation.id}>
                        <motion.button
                          type="button"
                          onClick={() => onSelect(conversation.id)}
                          className={className}
                          whileHover={{ x: 2 }}
                          whileTap={{ scale: 0.98 }}
                          transition={{ duration: 0.15 }}
                        >
                          {inner}
                        </motion.button>
                      </li>
                    )
                  }
                  return (
                    <li key={conversation.id}>
                      <button type="button" onClick={() => onSelect(conversation.id)} className={className}>
                        {inner}
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          <div className="border-t border-[var(--color-border)]/80 p-3">
            <p className="mb-2 px-2 text-[0.65rem] font-semibold uppercase tracking-widest text-[var(--color-text-muted)]">
              {t('agent.shortcuts')}
            </p>
            <nav className="space-y-0.5">
              {SHORTCUTS.map(({ to, icon: Icon, labelKey }) => (
                <Link
                  key={to}
                  to={to}
                  className="flex items-center gap-2 rounded-lg px-2 py-2 text-sm text-[var(--color-text-muted)] transition hover:bg-[var(--color-surface-muted)] hover:text-[var(--color-text)]"
                >
                  <Icon className="h-4 w-4 shrink-0 opacity-70" />
                  {t(labelKey)}
                </Link>
              ))}
            </nav>
          </div>
        </>
      ) : null}
    </aside>
  )
}
