import { ChevronDown, ChevronUp, Eye, EyeOff, Info, Trash2 } from 'lucide-react'
import type { DraftCourse } from '../../types/planner'
import type { PlannerInsights } from '../../types/api'
import { useTranslation } from '../../i18n'
import { courseColor } from '../../lib/plannerColors'
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
  chooseFromGridHint?: string
  noScheduleHint?: string
  focused?: boolean
  onToggleActive: () => void
  onRemove: () => void
  onInfo: () => void
  onFocus?: () => void
  onMoveUp: () => void
  onMoveDown: () => void
  highlighted?: boolean
  onHover?: (courseNumber: string | null) => void
  readOnly?: boolean
  layout?: 'default' | 'compact'
}

export function SelectedCourseRow({
  course,
  index,
  total,
  conflict,
  prereqWarning,
  staleWarning,
  groupsSummary,
  chooseFromGridHint,
  noScheduleHint,
  focused,
  onToggleActive,
  onRemove,
  onInfo,
  onFocus,
  onMoveUp,
  onMoveDown,
  highlighted,
  onHover,
  readOnly,
  layout = 'default',
}: SelectedCourseRowProps) {
  const { t } = useTranslation()
  const inactive = course.isActive === false
  const color = courseColor(course.courseNumber, course.color)
  const compact = layout === 'compact'

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onFocus}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onFocus?.()
        }
      }}
      className={cn(
        'snap-start rounded-xl border transition',
        compact ? 'w-60 shrink-0 px-2.5 py-2.5' : 'px-3 py-3',
        inactive
          ? 'border-[var(--color-border)] bg-[var(--color-surface-muted)]/60 opacity-60'
          : 'border-[var(--color-border)] bg-[var(--color-surface-muted)]',
        (highlighted || focused) && 'ring-2 ring-[var(--color-primary)]/40',
        onFocus && 'cursor-pointer hover:border-[var(--color-primary)]/30',
      )}
      onMouseEnter={() => onHover?.(course.courseNumber)}
      onMouseLeave={() => onHover?.(null)}
    >
      <div className="flex items-start gap-2">
        <span className="mt-1 h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: color }} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs font-semibold text-[var(--color-primary)]">{course.courseNumber}</p>
          <p
            className={cn(
              'mt-0.5 font-medium leading-snug text-[var(--color-text)]',
              compact ? 'line-clamp-2 text-xs' : 'text-sm',
            )}
          >
            {course.courseTitle}
          </p>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {formatCredits(course.credits)} {t('common.credits')}
            {inactive ? ` · ${t('planner.inactive')}` : ''}
          </p>
          {groupsSummary ? (
            <p className={cn('mt-1 text-[var(--color-primary)]', compact ? 'line-clamp-2 text-[10px] leading-relaxed' : 'text-xs leading-relaxed')}>
              {groupsSummary}
            </p>
          ) : chooseFromGridHint ? (
            <p className="mt-1 text-[10px] text-[var(--color-warning)]">{chooseFromGridHint}</p>
          ) : noScheduleHint ? (
            <p className="mt-1 text-[10px] text-[var(--color-text-muted)]">{noScheduleHint}</p>
          ) : null}
        </div>
        {!readOnly && !compact ? (
          <div className="flex shrink-0 flex-col gap-0.5">
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('planner.moveUp')}
              disabled={index === 0}
              onClick={(e) => {
                e.stopPropagation()
                onMoveUp()
              }}
              className="!h-6 !w-6 !p-0"
            >
              <ChevronUp className="h-3.5 w-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              aria-label={t('planner.moveDown')}
              disabled={index >= total - 1}
              onClick={(e) => {
                e.stopPropagation()
                onMoveDown()
              }}
              className="!h-6 !w-6 !p-0"
            >
              <ChevronDown className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : null}
      </div>

      <div className={cn('flex flex-wrap justify-end gap-1 border-t border-[var(--color-border)]/60 pt-2', compact ? 'mt-1.5' : 'mt-2')}>
        {!readOnly ? (
          <Button
            variant="ghost"
            size="sm"
            title={inactive ? t('planner.includeInSchedule') : t('planner.excludeFromSchedule')}
            aria-label={inactive ? t('planner.includeInSchedule') : t('planner.excludeFromSchedule')}
            aria-pressed={!inactive}
            onClick={(e) => {
              e.stopPropagation()
              onToggleActive()
            }}
          >
            {inactive ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </Button>
        ) : null}
        <Button
          variant="ghost"
          size="sm"
          aria-label={t('planner.courseInfo')}
          onClick={(e) => {
            e.stopPropagation()
            onInfo()
          }}
        >
          <Info className="h-4 w-4" />
        </Button>
        {!readOnly ? (
          <Button
            variant="ghost"
            size="sm"
            aria-label={t('plans.removeCourse')}
            onClick={(e) => {
              e.stopPropagation()
              onRemove()
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        ) : null}
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
  if (warning.status === 'missing' || warning.status === 'possibly_missing' || warning.status === 'unknown_course') {
    return { tone: 'danger', message: warning.message ?? 'Prerequisites may be missing' }
  }
  if (warning.status === 'manual_verification') {
    return { tone: 'warning', message: warning.message ?? 'Verify prerequisites manually' }
  }
  return null
}
