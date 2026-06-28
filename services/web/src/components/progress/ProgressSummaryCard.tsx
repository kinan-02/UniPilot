import { Layers, Target } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { interpolateTemplate } from '../../lib/electivePools'
import { progressCatalogSubtitle, statusBadgeTone } from '../../lib/graduationProgress'
import { formatCredits, formatPercent } from '../../lib/utils'
import type { GraduationProgress } from '../../types/api'

type ProgressSummaryCardProps = {
  progress: GraduationProgress
  statusLabel: string
  attentionCount?: number
  t: (key: string) => string
}

function SummaryStat({
  icon: Icon,
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  icon: typeof Target
  label: string
  value: string
  hint?: string
  tone?: 'neutral' | 'primary' | 'warning' | 'success'
}) {
  const toneClass =
    tone === 'primary'
      ? 'border-[var(--color-primary)]/15 bg-[var(--color-primary)]/5'
      : tone === 'warning'
        ? 'border-amber-200 bg-amber-50/80'
        : tone === 'success'
          ? 'border-emerald-200 bg-emerald-50/80'
          : 'border-[var(--color-border)] bg-white/80'

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
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
          {label}
        </p>
      </div>
      <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">{hint}</p> : null}
    </div>
  )
}

export function ProgressSummaryCard({
  progress,
  statusLabel,
  attentionCount = 0,
  t,
}: ProgressSummaryCardProps) {
  const catalogLabel = progressCatalogSubtitle(progress)
  const completionPercent = Math.min(progress.completionPercentage, 100)
  const electiveCompleted = progress.completedElectiveCredits ?? 0
  const electiveRemaining = progress.remainingElectiveCredits ?? 0
  const electiveTotal = electiveCompleted + electiveRemaining
  const electivePercent =
    electiveTotal > 0 ? Math.min(100, (electiveCompleted / electiveTotal) * 100) : 0

  return (
    <Card className="overflow-hidden p-0" data-testid="progress-summary-card">
      <div className="border-b border-[var(--color-border)] bg-gradient-to-br from-white via-white to-[var(--color-surface-muted)]/60 px-6 py-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {catalogLabel ? (
              <p className="text-sm font-medium text-[var(--color-text)]">{catalogLabel}</p>
            ) : null}
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">
              {t('progress.summarySubtitle')}
            </p>
          </div>
          <Badge tone={statusBadgeTone(progress.statusSummary)}>{statusLabel}</Badge>
        </div>

        <div className="mt-5 flex flex-wrap items-end gap-4">
          <p className="text-5xl font-semibold tabular-nums tracking-tight">
            {formatPercent(completionPercent)}
          </p>
          <div className="pb-1">
            <p className="text-sm font-medium">{t('progress.overallCompletion')}</p>
            <p className="text-xs text-[var(--color-text-muted)]">
              {formatCredits(progress.completedCredits)} / {formatCredits(progress.totalRequiredCredits)}{' '}
              {t('common.credits').toLowerCase()}
            </p>
          </div>
        </div>

        {attentionCount > 0 ? (
          <a
            href="#progress-attention"
            className="mt-4 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 transition hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-400/40"
            data-testid="progress-summary-attention-link"
          >
            {interpolateTemplate(t('progress.summaryAttentionLink'), { count: attentionCount })}
          </a>
        ) : null}

        <div className="mt-4">
          <div className="mb-2 flex justify-between text-xs tabular-nums text-[var(--color-text-muted)]">
            <span>{formatCredits(progress.completedCredits)}</span>
            <span>{formatCredits(progress.totalRequiredCredits)}</span>
          </div>
          <div className="h-3 overflow-hidden rounded-full bg-stone-100">
            <div
              className="h-full rounded-full bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-accent)] transition-all duration-700"
              style={{ width: `${completionPercent}%` }}
            />
          </div>
        </div>
      </div>

      <div className="grid gap-3 px-6 py-5 sm:grid-cols-2">
        <SummaryStat
          icon={Target}
          label={t('progress.creditsRemaining')}
          value={formatCredits(progress.creditsRemaining)}
          hint={`${formatCredits(progress.completedCredits)} ${t('progress.summaryEarned').toLowerCase()}`}
          tone={progress.creditsRemaining > 0 ? 'primary' : 'success'}
        />
        <SummaryStat
          icon={Layers}
          label={t('progress.electiveProgress')}
          value={formatCredits(electiveCompleted)}
          hint={
            electiveTotal > 0
              ? `${formatPercent(electivePercent)} · ${formatCredits(electiveRemaining)} ${t('progress.electiveRemaining').toLowerCase()}`
              : t('progress.summaryNoElectiveCredits')
          }
          tone="neutral"
        />
      </div>
    </Card>
  )
}
