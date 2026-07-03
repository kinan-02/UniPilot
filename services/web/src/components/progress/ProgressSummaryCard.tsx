import { AlertCircle, BookOpenCheck, GraduationCap, Sparkles } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { interpolateTemplate } from '../../lib/electivePools'
import { progressCatalogSubtitle, statusBadgeTone, hasDegreeCreditBucketGap } from '../../lib/graduationProgress'
import { formatCredits, formatPercent } from '../../lib/utils'
import type { GraduationProgress } from '../../types/api'

type ProgressSummaryCardProps = {
  progress: GraduationProgress
  statusLabel: string
  attentionCount?: number
  mandatoryRemainingCount?: number
  t: (key: string) => string
  id?: string
}

function SummaryStat({
  icon: Icon,
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  icon: typeof GraduationCap
  label: string
  value: string
  hint?: string
  tone?: 'neutral' | 'primary' | 'warning' | 'success'
}) {
  const toneClass =
    tone === 'primary'
      ? 'border-[var(--color-primary)]/15 bg-[var(--color-primary)]/5'
      : tone === 'warning'
        ? 'border-amber-200/80 bg-amber-50/70'
        : tone === 'success'
          ? 'border-emerald-200/80 bg-emerald-50/70'
          : 'border-[var(--color-border)] bg-white/90'

  const iconClass =
    tone === 'primary'
      ? 'text-[var(--color-primary)]'
      : tone === 'warning'
        ? 'text-amber-700'
        : tone === 'success'
          ? 'text-emerald-700'
          : 'text-[var(--color-text-muted)]'

  return (
    <div className={`rounded-xl border px-4 py-3 ${toneClass}`}>
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 shrink-0 ${iconClass}`} aria-hidden />
        <p className="text-xs font-medium text-[var(--color-text-muted)]">{label}</p>
      </div>
      <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? (
        <p className="mt-1 text-xs leading-snug text-[var(--color-text-muted)] text-pretty">{hint}</p>
      ) : null}
    </div>
  )
}

export function ProgressSummaryCard({
  progress,
  statusLabel,
  attentionCount = 0,
  mandatoryRemainingCount = 0,
  t,
  id = 'progress-overview',
}: ProgressSummaryCardProps) {
  const catalogLabel = progressCatalogSubtitle(progress)
  const completionPercent = Math.min(progress.completionPercentage, 100)
  const electiveCompleted = progress.completedElectiveCredits ?? 0
  const electiveRemaining = progress.remainingElectiveCredits ?? 0
  const electiveTotal = electiveCompleted + electiveRemaining
  const showBucketGapNote = hasDegreeCreditBucketGap(progress)

  return (
    <Card
      className="scroll-mt-24 overflow-hidden p-0 shadow-sm"
      data-testid="progress-summary-card"
      id={id}
    >
      <div className="border-b border-[var(--color-border)] bg-gradient-to-br from-white via-white to-[var(--color-surface-muted)]/50 px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              {t('progress.summarySubtitle')}
            </p>
            {catalogLabel ? (
              <p className="mt-1 text-sm font-medium text-balance text-[var(--color-text)]">
                {catalogLabel}
              </p>
            ) : null}
          </div>
          <Badge tone={statusBadgeTone(progress.statusSummary)}>{statusLabel}</Badge>
        </div>

        <div className="mt-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <p className="text-sm font-medium text-[var(--color-text-muted)]">
              {t('progress.creditsTowardDegree')}
            </p>
            <p
              className="mt-1 text-4xl font-semibold tabular-nums tracking-tight sm:text-5xl"
              data-testid="progress-credits-hero"
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
            {showBucketGapNote ? (
              <p className="mt-2 text-xs text-amber-800 text-pretty">
                {t('progress.bucketCompletionMismatch')}
              </p>
            ) : null}
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
            <div className="hidden min-w-[6rem] sm:block">
              <p className="text-xs font-medium text-[var(--color-text-muted)]">
                {t('progress.overallCompletion')}
              </p>
              <p className="text-sm font-medium text-[var(--color-text)]">
                {formatCredits(progress.completedCredits)} {t('common.credits')}
              </p>
            </div>
          </div>
        </div>

        <div className="mt-5">
          <div className="mb-2 flex justify-between text-xs tabular-nums text-[var(--color-text-muted)]">
            <span>0</span>
            <span>{formatCredits(progress.totalRequiredCredits)}</span>
          </div>
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

        {attentionCount > 0 ? (
          <a
            href="#progress-attention"
            className="mt-4 inline-flex items-center gap-2 rounded-full border border-amber-200/90 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-950 transition hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/40"
            data-testid="progress-summary-attention-link"
          >
            <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden />
            {interpolateTemplate(t('progress.summaryAttentionLink'), { count: attentionCount })}
          </a>
        ) : null}
      </div>

      <div className="grid gap-3 px-5 py-4 sm:grid-cols-3 sm:px-6 sm:py-5">
        <SummaryStat
          icon={Sparkles}
          label={t('progress.creditsRemaining')}
          value={formatCredits(progress.creditsRemaining)}
          hint={t('progress.summaryRemainingHint')}
          tone={progress.creditsRemaining > 0 ? 'primary' : 'success'}
        />
        <SummaryStat
          icon={BookOpenCheck}
          label={t('progress.electiveProgress')}
          value={
            electiveTotal > 0
              ? `${formatCredits(electiveCompleted)} / ${formatCredits(electiveTotal)}`
              : formatCredits(electiveCompleted)
          }
          hint={
            electiveTotal > 0
              ? interpolateTemplate(t('progress.summaryElectiveHint'), {
                  remaining: formatCredits(electiveRemaining),
                })
              : t('progress.summaryNoElectiveCredits')
          }
          tone="neutral"
        />
        <SummaryStat
          icon={GraduationCap}
          label={t('progress.mandatoryRemaining')}
          value={String(mandatoryRemainingCount)}
          hint={t('progress.summaryMandatoryHint')}
          tone={mandatoryRemainingCount > 0 ? 'warning' : 'success'}
        />
      </div>
    </Card>
  )
}
