import type { ExamSummary } from '../../types/api'
import { useTranslation } from '../../i18n'
import { Badge, Card } from '../ui/Card'

type ExamSummaryPanelProps = {
  summary?: ExamSummary
  className?: string
}

export function ExamSummaryPanel({ summary, className }: ExamSummaryPanelProps) {
  const { t } = useTranslation()
  const exams = summary?.exams ?? []
  const warnings = summary?.warnings ?? []

  if (!exams.length) {
    return (
      <Card className={className}>
        <h3 className="text-sm font-semibold">{t('planner.examsTitle')}</h3>
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">{t('planner.noExams')}</p>
      </Card>
    )
  }

  return (
    <Card className={className}>
      <h3 className="text-sm font-semibold">{t('planner.examsTitle')}</h3>
      {warnings.length ? (
        <div className="mt-3 space-y-1">
          {warnings.map((warning, index) => (
            <p key={index} className="text-xs text-[var(--color-warning)]">
              {warning.message}
            </p>
          ))}
        </div>
      ) : null}
      <ul className="mt-4 space-y-2">
        {exams.map((exam, index) => (
          <li
            key={`${exam.courseNumber}-${exam.moed}-${index}`}
            className={`rounded-lg border px-3 py-2 text-sm ${
              exam.isMissing
                ? 'border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5'
                : 'border-[var(--color-border)] bg-[var(--color-surface-muted)]'
            }`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-xs text-[var(--color-primary)]">{exam.courseNumber}</span>
              {exam.moed ? <Badge tone="neutral">Moed {exam.moed}</Badge> : null}
              {exam.isMissing ? (
                <Badge tone="warning">{t('planner.examMissing')}</Badge>
              ) : null}
            </div>
            <p className="font-medium">{exam.courseName}</p>
            <p className="text-xs text-[var(--color-text-muted)]">
              {exam.date ?? exam.raw ?? t('planner.examUnknown')}
              {exam.startTime ? ` · ${exam.startTime}` : ''}
            </p>
          </li>
        ))}
      </ul>
    </Card>
  )
}
