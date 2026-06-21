import { ChevronDown, ChevronUp, Eye, EyeOff, Info, Layers, Trash2 } from 'lucide-react'
import type { DraftCourse } from './SemesterPlanner'
import type { PlannerInsights } from '../../types/api'
import { useTranslation } from '../../i18n'
import { formatCredits } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Card'
import { cn } from '../../lib/utils'

type SelectedCourseRowProps = {
  course: DraftCourse
  index: number
  total: number
  conflict: boolean
  prereqWarning?: { tone: 'warning' | 'danger'; message: string } | null
  staleWarning?: string
  groupsSummary?: string
  onToggleActive: () => void
  onRemove: () => void
  onInfo: () => void
  onEditGroups?: () => void
  onMoveUp: () => void
  onMoveDown: () => void
}

export function SelectedCourseRow({
  course,
  index,
  total,
  conflict,
  prereqWarning,
  staleWarning,
  groupsSummary,
  onToggleActive,
  onRemove,
  onInfo,
  onEditGroups,
  onMoveUp,
  onMoveDown,
}: SelectedCourseRowProps) {
  const { t } = useTranslation()
  const inactive = course.isActive === false

  return (
    <div
      className={cn(
        'rounded-xl border px-3 py-2 transition',
        inactive
          ? 'border-[var(--color-border)] bg-[var(--color-surface-muted)]/60 opacity-60'
          : 'border-[var(--color-border)] bg-[var(--color-surface-muted)]',
      )}
    >
      <div className="flex items-start gap-2">
        <div className="flex flex-col gap-0.5">
          <Button
            variant="ghost"
            size="sm"
            aria-label={t('planner.moveUp')}
            disabled={index === 0}
            onClick={onMoveUp}
            className="!h-6 !w-6 !p-0"
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            aria-label={t('planner.moveDown')}
            disabled={index >= total - 1}
            onClick={onMoveDown}
            className="!h-6 !w-6 !p-0"
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs text-[var(--color-primary)]">{course.courseNumber}</p>
          <p className="truncate text-sm font-medium">{course.courseTitle}</p>
          <p className="text-xs text-[var(--color-text-muted)]">
            {formatCredits(course.credits)} {t('common.credits')}
            {inactive ? ` · ${t('planner.inactive')}` : ''}
          </p>
          {groupsSummary ? (
            <p className="mt-0.5 text-xs text-[var(--color-primary)]">{groupsSummary}</p>
          ) : null}
        </div>
        {onEditGroups ? (
          <Button
            variant="ghost"
            size="sm"
            title={t('planner.editGroups')}
            aria-label={t('planner.editGroups')}
            onClick={onEditGroups}
          >
            <Layers className="h-4 w-4" />
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          title={inactive ? t('planner.includeInSchedule') : t('planner.excludeFromSchedule')}
          aria-label={inactive ? t('planner.includeInSchedule') : t('planner.excludeFromSchedule')}
          aria-pressed={!inactive}
          onClick={onToggleActive}
        >
          {inactive ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </Button>
        <Button variant="ghost" size="sm" aria-label={t('planner.courseInfo')} onClick={onInfo}>
          <Info className="h-4 w-4" />
        </Button>
        <Button variant="ghost" size="sm" aria-label={t('plans.removeCourse')} onClick={onRemove}>
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
      {(conflict || prereqWarning || staleWarning) && (
        <div className="mt-2 space-y-1">
          {conflict && !inactive ? <Badge tone="warning">{t('plans.scheduleConflicts')}</Badge> : null}
          {staleWarning ? (
            <p className="text-xs text-[var(--color-warning)]">{staleWarning}</p>
          ) : null}
          {prereqWarning && !inactive ? (
            <p
              className={`text-xs ${
                prereqWarning.tone === 'danger'
                  ? 'text-[var(--color-danger)]'
                  : 'text-[var(--color-warning)]'
              }`}
            >
              {prereqWarning.message}
            </p>
          ) : null}
        </div>
      )}
    </div>
  )
}

export function warningForCourse(
  insights: PlannerInsights | undefined,
  courseId: string,
): { tone: 'warning' | 'danger'; message: string } | null {
  const warning = insights?.courseWarnings?.find((item) => item.courseId === courseId)
  if (!warning) return null
  if (warning.status === 'missing' || warning.status === 'possibly_missing') {
    return { tone: 'danger', message: warning.message ?? 'Prerequisites may be missing' }
  }
  if (warning.status === 'manual_verification') {
    return { tone: 'warning', message: warning.message ?? 'Verify prerequisites manually' }
  }
  return null
}
