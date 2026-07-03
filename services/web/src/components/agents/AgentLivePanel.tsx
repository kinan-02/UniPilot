import {
  Bot,
  Brain,
  ClipboardCheck,
  GraduationCap,
  Scale,
  Search,
  Shield,
  Sparkles,
  Target,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge, Spinner } from '../ui/Card'
import { cn } from '../../lib/utils'

export const LIVE_ROLE_ICONS: Record<string, LucideIcon> = {
  goal_analyst: Target,
  planner: Brain,
  catalog_scout: Search,
  risk_sentinel: Shield,
  student_advocate: GraduationCap,
  arbiter: Scale,
  progress_scout: ClipboardCheck,
  explainer: Sparkles,
  red_team: Shield,
  policy_responder: Bot,
}

export function resolveLiveEventRole(event: Record<string, unknown>): string | null {
  const agentRole = event.agent_role ?? event.agentRole
  if (typeof agentRole === 'string' && agentRole.trim()) {
    return agentRole.trim()
  }
  const phase = event.phase
  if (typeof phase === 'string') {
    const lowered = phase.toLowerCase()
    if (lowered.includes('planner')) return 'planner'
    if (lowered.includes('scout') || lowered.includes('catalog')) return 'catalog_scout'
    if (lowered.includes('sentinel') || lowered.includes('risk')) return 'risk_sentinel'
    if (lowered.includes('advocate')) return 'student_advocate'
    if (lowered.includes('arbiter')) return 'arbiter'
    if (lowered.includes('goal')) return 'goal_analyst'
  }
  return null
}

type AgentLivePanelProps = {
  negotiatingLabel: string
  streamTitle: string
  events: Array<Record<string, unknown>>
  connected: boolean
  connectedLabel: string
  connectingLabel: string
  roleLabel: (role: string) => string
  eventLabel: (event: Record<string, unknown>) => string
}

export function AgentLivePanel({
  negotiatingLabel,
  streamTitle,
  events,
  connected,
  connectedLabel,
  connectingLabel,
  roleLabel,
  eventLabel,
}: AgentLivePanelProps) {
  const latestRole = events.length > 0 ? resolveLiveEventRole(events[events.length - 1] ?? {}) : null
  const LatestIcon = latestRole ? LIVE_ROLE_ICONS[latestRole] ?? Bot : Bot

  return (
    <div className="space-y-4" data-testid="agent-sessions-live-panel">
      <div className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-gradient-to-br from-white via-white to-[var(--color-primary)]/8 shadow-sm">
        <div className="flex items-center gap-4 px-4 py-4 sm:px-5">
          <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
            <LatestIcon className="h-6 w-6" aria-hidden />
            <span className="absolute -end-0.5 -top-0.5 flex h-3.5 w-3.5">
              <Spinner className="h-3.5 w-3.5" />
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">{negotiatingLabel}</p>
            {latestRole ? (
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                {roleLabel(latestRole)}
              </p>
            ) : null}
            <p className="mt-1 flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
              <span
                className={cn(
                  'inline-block h-2 w-2 rounded-full',
                  connected ? 'bg-emerald-500 animate-pulse' : 'bg-stone-400',
                )}
                aria-hidden
              />
              {connected ? connectedLabel : connectingLabel}
            </p>
          </div>
        </div>
      </div>

      {events.length > 0 ? (
        <div data-testid="agent-sessions-live-stream">
          <p className="mb-3 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            {streamTitle}
          </p>
          <ol className="space-y-2">
            {events.map((event, index) => {
              const role = resolveLiveEventRole(event)
              const Icon = role ? LIVE_ROLE_ICONS[role] ?? Bot : Bot
              const isLast = index === events.length - 1
              return (
                <li
                  key={`${String(event.event)}-${index}`}
                  className={cn(
                    'flex gap-3 rounded-xl border px-3 py-3 transition',
                    isLast
                      ? 'border-[var(--color-primary)]/30 bg-[var(--color-primary)]/5 shadow-sm'
                      : 'border-[var(--color-border)] bg-white',
                  )}
                >
                  <div
                    className={cn(
                      'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl',
                      isLast ? 'bg-[var(--color-primary)]/15 text-[var(--color-primary)]' : 'bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]',
                    )}
                  >
                    <Icon className="h-4 w-4" aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-[var(--color-text)]">
                        {eventLabel(event)}
                      </span>
                      {role ? (
                        <Badge tone="neutral">
                          {roleLabel(role)}
                        </Badge>
                      ) : null}
                      {typeof event.round === 'number' ? (
                        <span className="text-xs text-[var(--color-text-muted)]">
                          Round {event.round}
                        </span>
                      ) : null}
                    </div>
                    {typeof event.phase === 'string' ? (
                      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{event.phase}</p>
                    ) : null}
                  </div>
                </li>
              )
            })}
          </ol>
        </div>
      ) : null}
    </div>
  )
}
