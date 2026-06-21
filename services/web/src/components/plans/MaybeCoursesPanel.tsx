import type { ReactNode } from 'react'
import { Sparkles } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'
import { Card } from '../ui/Card'

type MaybeCoursesPanelProps = {
  courseCount: number
  children: ReactNode
  className?: string
}

export function MaybeCoursesPanel({ courseCount, children, className }: MaybeCoursesPanelProps) {
  const { t } = useTranslation()

  return (
    <Card className={cn('flex min-h-0 flex-col print:hidden', className)} data-testid="maybe-courses-panel">
      <div className="mb-2 shrink-0">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{t('planner.maybeCourses')}</h3>
          {courseCount ? (
            <span className="text-xs text-[var(--color-text-muted)]">
              {courseCount} {t('plans.coursesCount')}
            </span>
          ) : null}
        </div>
        <p className="mt-0.5 text-[11px] leading-snug text-[var(--color-text-muted)]">
          {t('planner.maybeCoursesHint')}
        </p>
      </div>

      {courseCount ? (
        <div className="max-h-48 min-h-0 flex-1 space-y-1 overflow-y-auto xl:max-h-56">
          {children}
        </div>
      ) : (
        <div className="flex items-center gap-3 rounded-lg border border-dashed border-[var(--color-border)] px-3 py-4">
          <Sparkles className="h-6 w-6 shrink-0 text-[var(--color-text-muted)]" />
          <div>
            <p className="text-sm font-medium">{t('planner.emptyMaybeTitle')}</p>
            <p className="text-xs text-[var(--color-text-muted)]">{t('planner.emptyMaybeHint')}</p>
          </div>
        </div>
      )}
    </Card>
  )
}
