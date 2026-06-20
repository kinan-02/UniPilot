import { BookOpen, CalendarDays, Target } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { semesterLabel } from '../../lib/semester'
import { formatCredits } from '../../lib/utils'
import { cn } from '../../lib/utils'

type PlanBuilderSummaryProps = {
  name: string
  semesterCode: string
  courseCount: number
  totalCredits: number
  goalCredits: number | null
  stepLabel: string
  className?: string
}

export function PlanBuilderSummary({
  name,
  semesterCode,
  courseCount,
  totalCredits,
  goalCredits,
  stepLabel,
  className,
}: PlanBuilderSummaryProps) {
  const { t, locale } = useTranslation()
  const goal = goalCredits ?? 0
  const progress =
    goal > 0 ? Math.min(100, Math.round((totalCredits / goal) * 100)) : null

  return (
    <aside
      className={cn(
        'rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-soft)]',
        className,
      )}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
        {stepLabel}
      </p>
      <h3 className="mt-2 text-lg font-semibold tracking-tight">
        {name.trim() || t('plans.unnamedPlan')}
      </h3>
      <p className="mt-1 text-sm text-[var(--color-text-muted)]">
        {semesterLabel(semesterCode, locale)}
      </p>

      <div className="mt-5 space-y-3">
        <div className="flex items-center gap-3 text-sm">
          <BookOpen className="h-4 w-4 text-[var(--color-primary)]" />
          <span>
            {courseCount} {t('plans.coursesCount')}
          </span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <Target className="h-4 w-4 text-[var(--color-primary)]" />
          <span>
            {formatCredits(totalCredits)} {t('common.credits')}
            {goal > 0 ? ` / ${formatCredits(goal)}` : ''}
          </span>
        </div>
        <div className="flex items-center gap-3 text-sm">
          <CalendarDays className="h-4 w-4 text-[var(--color-primary)]" />
          <span className="font-mono text-xs">{semesterCode}</span>
        </div>
      </div>

      {progress !== null ? (
        <div className="mt-5">
          <div className="mb-1 flex justify-between text-xs text-[var(--color-text-muted)]">
            <span>{t('plans.creditProgress')}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--color-surface-muted)]">
            <div
              className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-300"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      ) : null}
    </aside>
  )
}
