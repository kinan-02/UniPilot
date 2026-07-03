import { History } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { cn } from '../../lib/utils'
import { useTranslation } from '../../i18n'
import type { AgentSession } from '../../types/api'
import { formatRelativeSessionTime, statusTone } from './agentSessionUtils'

type AgentHistoryPanelProps = {
  sessions: AgentSession[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  title: string
  statusLabel: (status: string) => string
}

export function AgentHistoryPanel({
  sessions,
  activeSessionId,
  onSelect,
  title,
  statusLabel,
}: AgentHistoryPanelProps) {
  const { locale } = useTranslation()
  if (sessions.length === 0) return null

  return (
    <Card className="overflow-hidden p-0" data-testid="agent-sessions-history">
      <div className="flex items-center gap-2 border-b border-[var(--color-border)] px-4 py-3 sm:px-5">
        <History className="h-4 w-4 text-[var(--color-text-muted)]" aria-hidden />
        <p className="text-sm font-semibold">{title}</p>
      </div>
      <ul className="max-h-[min(420px,50vh)] divide-y divide-[var(--color-border)] overflow-y-auto">
        {sessions.map((session) => {
          const isActive = session.id === activeSessionId
          return (
            <li key={session.id}>
              <button
                type="button"
                onClick={() => onSelect(session.id)}
                className={cn(
                  'flex w-full items-start gap-3 px-4 py-3 text-start text-sm transition sm:px-5',
                  isActive
                    ? 'bg-[var(--color-primary)]/5 ring-1 ring-inset ring-[var(--color-primary)]/20'
                    : 'hover:bg-[var(--color-surface-muted)]/60',
                )}
              >
                <div className="min-w-0 flex-1">
                  <p className="line-clamp-2 font-medium text-[var(--color-text)]">{session.goal}</p>
                  <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                    {formatRelativeSessionTime(session.updatedAt, locale)}
                  </p>
                </div>
                <Badge tone={statusTone(session.status)}>{statusLabel(session.status)}</Badge>
              </button>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
