import { Bot, CheckCircle2, MessageSquare, ShieldAlert, Sparkles } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '../ui/Card'
import { formatAgentRole } from './agentSessionUtils'
import type { AgentTurn } from '../../types/api'

const ROLE_ICONS: Record<string, LucideIcon> = {
  planner: Sparkles,
  catalog_scout: Bot,
  risk_sentinel: ShieldAlert,
  progress_scout: CheckCircle2,
  student_advocate: MessageSquare,
  arbiter: CheckCircle2,
  goal_analyst: Bot,
  policy_responder: MessageSquare,
  red_team: ShieldAlert,
  explainer: MessageSquare,
}

function actionTone(action: string): 'success' | 'warning' | 'neutral' | 'danger' {
  if (action === 'veto') return 'danger'
  if (action === 'commit') return 'success'
  if (action === 'revise') return 'warning'
  return 'neutral'
}

type AgentTranscriptTimelineProps = {
  turns: AgentTurn[]
  title: string
  actionLabel: (action: string) => string
  renderReasoning?: (turn: AgentTurn) => React.ReactNode
}

export function AgentTranscriptTimeline({
  turns,
  title,
  actionLabel,
  renderReasoning,
}: AgentTranscriptTimelineProps) {
  if (turns.length === 0) return null

  return (
    <section
      className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-sm"
      data-testid="agent-sessions-transcript"
    >
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-4 py-3 sm:px-5">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{title}</h3>
      </header>
      <div className="px-4 py-4 sm:px-5">
        <ol className="relative space-y-0 border-s-2 border-[var(--color-border)] ps-6">
        {turns.map((turn, index) => {
          const Icon = ROLE_ICONS[turn.agent_role] ?? Bot
          const isLast = index === turns.length - 1
          return (
            <li key={`${turn.agent_role}-${turn.action}-${index}`} className="relative pb-5 last:pb-0">
              <span
                className={`absolute -start-[1.875rem] top-1 flex h-7 w-7 items-center justify-center rounded-full border-2 border-white bg-white shadow-sm ${
                  isLast ? 'text-[var(--color-primary)]' : 'text-stone-400'
                }`}
              >
                <Icon className="h-3.5 w-3.5" aria-hidden />
              </span>
              <div className="rounded-xl border border-[var(--color-border)] bg-white p-3 shadow-sm">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium capitalize">
                    {formatAgentRole(turn.agent_role)}
                  </span>
                  <Badge tone={actionTone(turn.action)}>{actionLabel(turn.action)}</Badge>
                </div>
                {turn.rationale ? (
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-[var(--color-text-muted)]">
                    {turn.rationale}
                  </p>
                ) : null}
                {renderReasoning ? renderReasoning(turn) : null}
                {turn.references.length > 0 ? (
                  <details className="mt-2 text-xs text-[var(--color-text-muted)]">
                    <summary className="cursor-pointer font-medium">Sources</summary>
                    <ul className="mt-1 list-disc ps-4">
                      {turn.references.slice(0, 6).map((reference) => (
                        <li key={reference} className="break-all">
                          {reference}
                        </li>
                      ))}
                    </ul>
                  </details>
                ) : null}
              </div>
            </li>
          )
        })}
        </ol>
      </div>
    </section>
  )
}
