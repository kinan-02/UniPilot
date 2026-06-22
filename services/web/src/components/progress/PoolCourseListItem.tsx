import { memo } from 'react'
import { Link } from 'react-router-dom'
import { CheckCircle2 } from 'lucide-react'
import { catalogSearchLink } from '../../lib/electivePools'
import { cn, formatCredits } from '../../lib/utils'
import type { ElectivePoolCourse } from '../../types/api'

type PoolCourseListItemProps = {
  course: ElectivePoolCourse
  displayTitle?: string
  isCounted: boolean
  isRequiredCurriculum?: boolean
  countedLabel: string
  requiredLabel?: string
  showChainStep?: boolean
  stepNumber?: number
  showConnector?: boolean
  compact?: boolean
  as?: 'li' | 'div'
}

export const PoolCourseListItem = memo(function PoolCourseListItem({
  course,
  displayTitle,
  isCounted,
  isRequiredCurriculum = false,
  countedLabel,
  requiredLabel,
  showChainStep = false,
  stepNumber,
  showConnector = false,
  compact = false,
  as = 'li',
}: PoolCourseListItemProps) {
  const Tag = as

  return (
    <Tag
      role={as === 'div' ? 'listitem' : undefined}
      className={cn(
        showChainStep && 'relative ps-9',
        showChainStep &&
          showConnector &&
          'pb-3 before:absolute before:start-[1.05rem] before:top-9 before:h-[calc(100%-1.25rem)] before:w-px before:bg-[var(--color-border)]',
      )}
    >
      {showChainStep ? (
        <span
          className={cn(
            'absolute start-0 top-2 flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold',
            isCounted
              ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
              : 'border-[var(--color-border)] bg-white text-[var(--color-text-muted)]',
          )}
        >
          {stepNumber}
        </span>
      ) : null}
      <div
        className={cn(
          'flex items-start justify-between gap-3 rounded-xl border text-sm transition',
          compact ? 'px-3 py-2' : 'px-3 py-2.5',
          isCounted
            ? 'border-emerald-200 bg-emerald-50/80'
            : isRequiredCurriculum
              ? 'border-sky-200 bg-sky-50/70'
              : 'border-[var(--color-border)] bg-white hover:border-[var(--color-primary)]/25 hover:shadow-sm',
        )}
      >
        <div className="min-w-0 flex-1">
          <Link
            to={catalogSearchLink(course.courseNumber)}
            className="font-mono text-xs font-semibold text-[var(--color-primary)] hover:underline"
            onClick={(event) => event.stopPropagation()}
          >
            {course.courseNumber}
          </Link>
          <p className={cn('leading-snug', compact ? 'mt-0.5 line-clamp-1 text-xs' : 'mt-0.5')}>
            {displayTitle ?? course.title ?? course.courseNumber}
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-1 text-xs text-[var(--color-text-muted)]">
          {course.credits != null ? <span className="tabular-nums">{formatCredits(course.credits)}</span> : null}
          {isRequiredCurriculum ? (
            <span className="inline-flex items-center gap-1 font-medium text-sky-800">
              {requiredLabel}
            </span>
          ) : null}
          {isCounted ? (
            <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
              <CheckCircle2 className="h-3.5 w-3.5" />
              {countedLabel}
            </span>
          ) : null}
        </div>
      </div>
    </Tag>
  )
})
