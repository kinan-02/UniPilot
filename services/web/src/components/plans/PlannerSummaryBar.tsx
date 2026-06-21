import { useTranslation } from '../../i18n'
import { formatCredits } from '../../lib/utils'
import { cn } from '../../lib/utils'

type PlannerSummaryBarProps = {
  activeCount: number
  totalCount: number
  activeCredits: number
  conflictCount: number
  examCount: number
  maxCredits?: number
  className?: string
}

export function PlannerSummaryBar({
  activeCount,
  totalCount,
  activeCredits,
  conflictCount,
  examCount,
  maxCredits,
  className,
}: PlannerSummaryBarProps) {
  const { t } = useTranslation()
  const overMax = maxCredits != null && activeCredits > maxCredits

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2.5 text-sm shadow-[var(--shadow-soft)]',
        className,
      )}
    >
      <span>
        <span className="text-[var(--color-text-muted)]">{t('planner.activeCourses')}:</span>{' '}
        <strong>{activeCount}</strong>
        {totalCount !== activeCount ? (
          <span className="text-[var(--color-text-muted)]"> / {totalCount}</span>
        ) : null}
      </span>
      <span>
        <span className="text-[var(--color-text-muted)]">{t('plans.totalCredits')}:</span>{' '}
        <strong className={overMax ? 'text-[var(--color-warning)]' : 'text-[var(--color-primary)]'}>
          {formatCredits(activeCredits)}
        </strong>
        {maxCredits != null ? (
          <span className="text-[var(--color-text-muted)]"> / {maxCredits}</span>
        ) : null}
      </span>
      <span>
        <span className="text-[var(--color-text-muted)]">{t('planner.conflicts')}:</span>{' '}
        <strong className={conflictCount ? 'text-[var(--color-warning)]' : ''}>{conflictCount}</strong>
      </span>
      <span>
        <span className="text-[var(--color-text-muted)]">{t('planner.examsCount')}:</span>{' '}
        <strong>{examCount}</strong>
      </span>
    </div>
  )
}
