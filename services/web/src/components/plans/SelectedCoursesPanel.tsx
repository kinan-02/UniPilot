import type { ReactNode } from 'react'
import { AlertTriangle, BookPlus } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'
import { Card } from '../ui/Card'

type SelectedCoursesPanelProps = {
  courseCount: number
  creditsWarning?: string
  coursesError?: string
  children: ReactNode
  className?: string
}

export function SelectedCoursesPanel({
  courseCount,
  creditsWarning,
  coursesError,
  children,
  className,
}: SelectedCoursesPanelProps) {
  const { t } = useTranslation()

  return (
    <Card className={cn('flex min-h-0 flex-col print:hidden', className)} data-testid="selected-courses-panel">
      <div className="mb-2 flex shrink-0 flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t('plans.selectedCourses')}</h3>
        {courseCount ? (
          <span className="text-xs text-[var(--color-text-muted)]">
            {courseCount} {t('plans.coursesCount')}
          </span>
        ) : null}
      </div>

      {creditsWarning ? (
        <p className="mb-2 flex shrink-0 items-start gap-2 text-xs text-[var(--color-warning)]">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          {creditsWarning}
        </p>
      ) : null}

      {courseCount ? (
        <div className="max-h-60 min-h-0 flex-1 space-y-1 overflow-y-auto xl:max-h-none">
          {children}
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-[var(--color-border)] px-4 py-5">
          <BookPlus className="h-7 w-7 shrink-0 text-[var(--color-text-muted)]" />
          <div>
            <p className="text-sm font-medium">{t('plans.emptyCoursesTitle')}</p>
            <p className="text-xs text-[var(--color-text-muted)]">{t('plans.emptyCoursesHint')}</p>
          </div>
        </div>
      )}

      {coursesError ? <p className="mt-2 shrink-0 text-xs text-[var(--color-danger)]">{coursesError}</p> : null}
    </Card>
  )
}
