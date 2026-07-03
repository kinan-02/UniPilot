import { Bot, Clock3, RotateCcw } from 'lucide-react'
import { Badge } from '../ui/Card'
import { formatSessionTimestamp } from './agentSessionUtils'

type AgentActiveSessionHeaderProps = {
  goal: string
  statusLabel: string
  statusToneValue: 'success' | 'warning' | 'neutral' | 'danger'
  activeSessionTitle: string
  updatedAt?: string | null
  rounds?: number
  updatedLabel: string
  roundsLabel: string
}

export function AgentActiveSessionHeader({
  goal,
  statusLabel,
  statusToneValue,
  activeSessionTitle,
  updatedAt,
  rounds,
  updatedLabel,
  roundsLabel,
}: AgentActiveSessionHeaderProps) {
  const formattedUpdated = formatSessionTimestamp(updatedAt)

  return (
    <header
      className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--color-border)] pb-4"
      data-testid="agent-sessions-active-header"
    >
      <div className="flex min-w-0 items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-[var(--color-primary)]/15 to-[var(--color-primary)]/5 text-[var(--color-primary)] shadow-sm">
          <Bot className="h-5 w-5" aria-hidden />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            {activeSessionTitle}
          </p>
          <h2 className="mt-1 line-clamp-3 text-base font-semibold leading-snug text-[var(--color-text)]">
            {goal}
          </h2>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-[var(--color-text-muted)]">
            {formattedUpdated ? (
              <span className="inline-flex items-center gap-1">
                <Clock3 className="h-3.5 w-3.5" aria-hidden />
                {updatedLabel}: {formattedUpdated}
              </span>
            ) : null}
            {typeof rounds === 'number' && rounds > 0 ? (
              <span className="inline-flex items-center gap-1">
                <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                {roundsLabel}: {rounds}
              </span>
            ) : null}
          </div>
        </div>
      </div>
      <Badge tone={statusToneValue} data-testid="agent-sessions-active-status">
        {statusLabel}
      </Badge>
    </header>
  )
}
