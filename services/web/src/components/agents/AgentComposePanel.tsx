import { Lightbulb, Play, Sparkles } from 'lucide-react'
import { AGENT_ROSTER } from './agentSessionUtils'
import {
  Brain,
  GraduationCap,
  Scale,
  Search,
  Shield,
  Target,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { cn } from '../../lib/utils'

const ROSTER_ICONS: Record<string, LucideIcon> = {
  goal_analyst: Target,
  planner: Brain,
  catalog_scout: Search,
  risk_sentinel: Shield,
  student_advocate: GraduationCap,
  arbiter: Scale,
}

type AgentComposePanelProps = {
  suggestedGoals: string[]
  goal: string
  onGoalChange: (value: string) => void
  onSubmitGoal: (goal: string) => void
  avoidFriday: boolean
  onAvoidFridayChange: (checked: boolean) => void
  isSubmitting: boolean
  errorMessage?: string | null
  title: string
  hint: string
  goalLabel: string
  goalPlaceholder: string
  startLabel: string
  avoidFridayLabel: string
  suggestionLabel: string
  rosterLabel: string
  roleLabel: (role: string) => string
}

export function AgentComposePanel({
  suggestedGoals,
  goal,
  onGoalChange,
  onSubmitGoal,
  avoidFriday,
  onAvoidFridayChange,
  isSubmitting,
  errorMessage,
  title,
  hint,
  goalLabel,
  goalPlaceholder,
  startLabel,
  avoidFridayLabel,
  suggestionLabel,
  rosterLabel,
  roleLabel,
}: AgentComposePanelProps) {
  return (
    <Card className="overflow-hidden p-0" data-testid="agent-sessions-compose">
      <div className="border-b border-[var(--color-border)] bg-gradient-to-br from-white to-[var(--color-surface-muted)]/50 px-4 py-4 sm:px-5">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
            <Sparkles className="h-5 w-5" aria-hidden />
          </div>
          <div>
            <p className="text-sm font-semibold">{title}</p>
            <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-muted)]">{hint}</p>
          </div>
        </div>
      </div>

      <div className="space-y-4 px-4 py-4 sm:px-5">
        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            {rosterLabel}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {AGENT_ROSTER.map(({ id }) => {
              const Icon = ROSTER_ICONS[id] ?? Brain
              return (
              <span
                key={id}
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-white px-2.5 py-1 text-[11px] font-medium text-[var(--color-text-muted)]"
              >
                <Icon className="h-3 w-3 text-[var(--color-primary)]" aria-hidden />
                {roleLabel(id)}
              </span>
              )
            })}
          </div>
        </div>

        <div className="space-y-2" data-testid="agent-sessions-suggestions">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            {suggestionLabel}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {suggestedGoals.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => onSubmitGoal(prompt)}
                className={cn(
                  'group rounded-xl border border-[var(--color-border)] bg-white px-3 py-3 text-start transition',
                  'hover:border-[var(--color-primary)]/35 hover:bg-[var(--color-surface-muted)]/50 hover:shadow-sm',
                )}
              >
                <span className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-primary)]/10 text-[var(--color-primary)] transition group-hover:bg-[var(--color-primary)]/15">
                    <Lightbulb className="h-3.5 w-3.5" aria-hidden />
                  </span>
                  <span className="min-w-0 text-sm font-medium leading-snug text-[var(--color-text)]">
                    {prompt}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <label className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2.5 text-sm">
          <input
            type="checkbox"
            checked={avoidFriday}
            onChange={(event) => onAvoidFridayChange(event.target.checked)}
            data-testid="agent-sessions-avoid-friday"
            className="h-4 w-4 rounded border-[var(--color-border)]"
          />
          {avoidFridayLabel}
        </label>

        <form
          onSubmit={(event) => {
            event.preventDefault()
            onSubmitGoal(goal)
          }}
          className="space-y-3"
        >
          <label className="block">
            <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              {goalLabel}
            </span>
            <textarea
              id="agent-session-goal"
              value={goal}
              onChange={(event) => onGoalChange(event.target.value)}
              placeholder={goalPlaceholder}
              rows={3}
              disabled={isSubmitting}
              data-testid="agent-sessions-goal-input"
              className="w-full resize-none rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-sm leading-relaxed outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20"
            />
          </label>
          <Button
            type="submit"
            loading={isSubmitting}
            disabled={!goal.trim()}
            className="w-full sm:w-auto"
            data-testid="agent-sessions-start"
          >
            <Play className="h-4 w-4" />
            {startLabel}
          </Button>
        </form>

        {errorMessage ? <p className="text-sm text-[var(--color-danger)]">{errorMessage}</p> : null}
      </div>
    </Card>
  )
}
