import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { interpolateTemplate } from '../../lib/electivePools'
import { progressCatalogSubtitle, statusBadgeTone } from '../../lib/graduationProgress'
import { formatCredits, formatPercent } from '../../lib/utils'
import type { GraduationProgress } from '../../types/api'

type DashboardProgressHeroProps = {
  progress: GraduationProgress | undefined
  progressLoading: boolean
  statusLabel: string
  t: (key: string) => string
}

export function DashboardProgressHero({
  progress,
  progressLoading,
  statusLabel,
  t,
}: DashboardProgressHeroProps) {
  if (progressLoading) {
    return (
      <Card className="animate-pulse space-y-4" data-testid="dashboard-progress-hero-loading">
        <div className="h-4 w-32 rounded bg-[var(--color-surface-muted)]" />
        <div className="h-10 w-40 rounded bg-[var(--color-surface-muted)]" />
        <div className="h-2.5 w-full rounded-full bg-[var(--color-surface-muted)]" />
      </Card>
    )
  }

  if (!progress) {
    return (
      <Card
        className="border-dashed bg-[var(--color-surface-muted)]/30"
        data-testid="dashboard-progress-empty"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">{t('dashboard.noProgressYet')}</p>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              {t('dashboard.noProgressHint')}
            </p>
          </div>
          <Link
            to="/transcript"
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white"
          >
            <BookOpen className="h-4 w-4" aria-hidden />
            {t('dashboard.importTranscript')}
          </Link>
        </div>
      </Card>
    )
  }

  const catalogLabel = progressCatalogSubtitle(progress)
  const completionPercent = Math.min(progress.completionPercentage, 100)

  return (
    <Card
      className="overflow-hidden p-0 shadow-sm"
      data-testid="dashboard-progress-hero"
    >
      <div className="border-b border-[var(--color-border)] bg-gradient-to-br from-white via-white to-[var(--color-surface-muted)]/50 px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              {t('dashboard.progressSnapshot')}
            </p>
            {catalogLabel ? (
              <p className="mt-1 text-sm font-medium text-balance">{catalogLabel}</p>
            ) : null}
          </div>
          <Badge tone={statusBadgeTone(progress.statusSummary)}>{statusLabel}</Badge>
        </div>

        <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-sm font-medium text-[var(--color-text-muted)]">
              {t('progress.creditsTowardDegree')}
            </p>
            <p
              className="mt-1 text-4xl font-semibold tabular-nums tracking-tight sm:text-5xl"
              data-testid="dashboard-credits-hero"
            >
              {formatCredits(progress.completedCredits)}
              <span className="text-2xl font-normal text-[var(--color-text-muted)] sm:text-3xl">
                {' '}
                / {formatCredits(progress.totalRequiredCredits)}
              </span>
            </p>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              {interpolateTemplate(t('progress.creditsRemainingInline'), {
                count: formatCredits(progress.creditsRemaining),
              })}
            </p>
          </div>

          <div
            className="flex shrink-0 items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-white/80 px-4 py-3"
            aria-label={t('progress.overallCompletion')}
          >
            <div
              className="relative flex h-14 w-14 items-center justify-center rounded-full"
              style={{
                background: `conic-gradient(var(--color-primary) ${completionPercent * 3.6}deg, rgb(245 245 244) 0deg)`,
              }}
            >
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-sm font-semibold tabular-nums">
                {formatPercent(completionPercent)}
              </div>
            </div>
          </div>
        </div>

        <div className="mt-5">
          <div
            className="h-2.5 overflow-hidden rounded-full bg-stone-100"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(completionPercent)}
            aria-label={t('progress.overallCompletion')}
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-accent)] transition-all duration-700 ease-out"
              style={{ width: `${completionPercent}%` }}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 sm:px-6">
        <p className="text-sm text-[var(--color-text-muted)]">{t('dashboard.progressSnapshotHint')}</p>
        <Link
          to="/progress"
          className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-primary)] transition hover:opacity-80"
          data-testid="dashboard-view-progress-link"
        >
          {t('dashboard.viewProgress')}
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    </Card>
  )
}
