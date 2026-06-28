import { Link } from 'react-router-dom'
import { CalendarDays, PartyPopper, ShieldCheck } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { formatCredits } from '../../lib/utils'
import type { GraduationProgress } from '../../types/api'

type ProgressCompletionCelebrationProps = {
  progress: GraduationProgress
  statusLabel: string
  t: (key: string, params?: Record<string, string | number>) => string
}

export function ProgressCompletionCelebration({
  progress,
  statusLabel,
  t,
}: ProgressCompletionCelebrationProps) {
  const isComplete = progress.statusSummary === 'complete'

  return (
    <Card
      className="overflow-hidden border-emerald-200 bg-gradient-to-br from-emerald-50/90 via-white to-white p-0"
      data-testid="progress-completion-celebration"
    >
      <div className="flex flex-wrap items-start gap-4 px-5 py-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-emerald-100 text-emerald-700">
          {isComplete ? <PartyPopper className="h-5 w-5" aria-hidden /> : <ShieldCheck className="h-5 w-5" aria-hidden />}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold">
              {isComplete ? t('progress.completion.titleComplete') : t('progress.completion.titleMandatoryMet')}
            </h2>
            <Badge tone="success">{statusLabel}</Badge>
          </div>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {isComplete
              ? t('progress.completion.subtitleComplete')
              : t('progress.completion.subtitleMandatoryMet', {
                  creditsRemaining: formatCredits(progress.creditsRemaining),
                  electiveRemaining: formatCredits(progress.remainingElectiveCredits ?? 0),
                })}
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to="/plans"
              className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-white px-3 py-2 text-sm font-medium text-emerald-900 transition hover:bg-emerald-50"
            >
              <CalendarDays className="h-4 w-4" aria-hidden />
              {t('progress.completion.planNextSemester')}
            </Link>
            <Link
              to="/risks"
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
            >
              {t('progress.completion.reviewRisks')}
            </Link>
          </div>
        </div>
      </div>
    </Card>
  )
}
