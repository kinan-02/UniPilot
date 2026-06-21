import { ArrowDown, ArrowUp, X } from 'lucide-react'
import type { DraftCourse } from '../../types/planner'
import { useTranslation } from '../../i18n'
import { courseColorStyles } from '../../lib/plannerColors'
import { cn, formatCredits } from '../../lib/utils'

type SelectedCourseListItemProps = {
  course: DraftCourse
  variant?: 'selected' | 'maybe'
  focused?: boolean
  highlighted?: boolean
  onFocus?: () => void
  onHover?: (courseNumber: string | null) => void
  onRemove?: () => void
  onMoveToOtherList?: () => void
  readOnly?: boolean
}

export function SelectedCourseListItem({
  course,
  variant = 'selected',
  focused,
  highlighted,
  onFocus,
  onHover,
  onRemove,
  onMoveToOtherList,
  readOnly,
}: SelectedCourseListItemProps) {
  const { t } = useTranslation()
  const inactive = course.isActive === false
  const colorStyles = courseColorStyles(course.courseNumber, course.color)
  const isMaybe = variant === 'maybe'

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
      onMouseEnter={() => onHover?.(course.courseNumber)}
      onMouseLeave={() => onHover?.(null)}
      className={cn(
        'group relative rounded-md border px-2.5 py-2 text-start transition',
        inactive && 'opacity-50',
        isMaybe && 'border-dashed',
        (highlighted || focused) && 'ring-2 ring-[var(--color-primary)]/50',
        onFocus && 'cursor-pointer hover:brightness-[0.98]',
      )}
      style={
        isMaybe
          ? {
              ...colorStyles,
              opacity: 0.88,
              backgroundImage:
                'repeating-linear-gradient(-45deg, transparent, transparent 8px, rgba(255,255,255,0.35) 8px, rgba(255,255,255,0.35) 16px)',
            }
          : colorStyles
      }
    >
      <div className={cn('min-w-0', !readOnly && (onRemove || onMoveToOtherList) && 'pe-14')}>
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-mono text-xs font-semibold">{course.courseNumber}</p>
          <p className="shrink-0 text-[11px] opacity-80">
            {formatCredits(course.credits)} {t('common.credits')}
          </p>
        </div>
        <p className="mt-0.5 text-sm leading-snug">{course.courseTitle}</p>
      </div>

      {!readOnly ? (
        <div className="absolute end-1 top-1.5 flex flex-col gap-0.5 opacity-70 transition group-hover:opacity-100">
          {onMoveToOtherList ? (
            <button
              type="button"
              aria-label={isMaybe ? t('planner.moveToSelected') : t('planner.moveToMaybe')}
              title={isMaybe ? t('planner.moveToSelected') : t('planner.moveToMaybe')}
              onClick={(e) => {
                e.stopPropagation()
                onMoveToOtherList()
              }}
              className="rounded-md p-1 hover:bg-black/5"
            >
              {isMaybe ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
            </button>
          ) : null}
          {onRemove ? (
            <button
              type="button"
              aria-label={t('plans.removeCourse')}
              onClick={(e) => {
                e.stopPropagation()
                onRemove()
              }}
              className="rounded-md p-1 hover:bg-black/5"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
