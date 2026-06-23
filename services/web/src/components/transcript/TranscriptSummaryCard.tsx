import { BookOpen, CalendarRange, ClipboardList, GraduationCap, Lock } from 'lucide-react'
import { Card } from '../ui/Card'
import { semesterLabel } from '../../lib/semester'
import { formatCredits, formatPercent } from '../../lib/utils'
import type { TranscriptStats } from '../../lib/transcript'
import type { Locale } from '../../i18n/types'

type TranscriptSummaryCardProps = {
  stats: TranscriptStats
  completionPercent?: number | null
  locale: Locale
  t: (key: string) => string
}

function SummaryStat({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: typeof BookOpen
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white/80 px-4 py-3">
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-[var(--color-text-muted)]" aria-hidden />
        <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
          {label}
        </p>
      </div>
      <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight">{value}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">{hint}</p> : null}
    </div>
  )
}

export function TranscriptSummaryCard({
  stats,
  completionPercent = null,
  locale,
  t,
}: TranscriptSummaryCardProps) {
  if (stats.courseCount === 0) return null

  const historyHint =
    stats.earliestSemesterCode && stats.latestSemesterCode
      ? t('transcript.historySpan')
          .replace(
            '{earliest}',
            semesterLabel(stats.earliestSemesterCode, locale),
          )
          .replace('{latest}', semesterLabel(stats.latestSemesterCode, locale))
      : null

  return (
    <Card className="overflow-hidden p-0" data-testid="transcript-summary-card">
      <div className="border-b border-[var(--color-border)] bg-gradient-to-br from-white via-white to-[var(--color-surface-muted)]/60 px-6 py-5">
        <p className="text-sm font-medium text-[var(--color-text)]">{t('transcript.summaryTitle')}</p>
        {historyHint ? (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">{historyHint}</p>
        ) : null}
        {stats.semesterCount > 0 ? (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {t('transcript.semestersRecorded').replace('{count}', String(stats.semesterCount))}
          </p>
        ) : null}
        {completionPercent != null ? (
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {t('progress.overallCompletion')}: {formatPercent(completionPercent)}
          </p>
        ) : null}
      </div>
      <div className="grid gap-3 p-6 sm:grid-cols-2 xl:grid-cols-5">
        <SummaryStat
          icon={ClipboardList}
          label={t('transcript.courses')}
          value={String(stats.courseCount)}
        />
        <SummaryStat
          icon={CalendarRange}
          label={t('common.semester')}
          value={String(stats.semesterCount)}
        />
        <SummaryStat
          icon={GraduationCap}
          label={t('transcript.totalCredits')}
          value={formatCredits(stats.totalCredits)}
        />
        <SummaryStat
          icon={BookOpen}
          label={t('transcript.averageGrade')}
          value={stats.averageGrade != null ? stats.averageGrade.toFixed(1) : '—'}
          hint={t('transcript.averageGradeHint')}
        />
        <SummaryStat
          icon={Lock}
          label={t('transcript.readOnlyEntries')}
          value={String(stats.readOnlyCount)}
          hint={
            stats.manualCount > 0
              ? `${stats.manualCount} ${t('transcript.manualEntries').toLowerCase()}`
              : undefined
          }
        />
      </div>
    </Card>
  )
}
