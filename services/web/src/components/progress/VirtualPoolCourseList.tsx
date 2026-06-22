import { useRef } from 'react'
import { useVirtualList } from '../../hooks/useVirtualList'
import { cn } from '../../lib/utils'
import { PoolCourseListItem } from './PoolCourseListItem'
import type { Locale } from '../../i18n/types'
import { localizedCourseTitle } from '../../lib/electivePools'
import type { ElectivePoolCourse } from '../../types/api'

const COMPACT_ROW_HEIGHT = 64
const REGULAR_ROW_HEIGHT = 76
const CHAIN_ROW_HEIGHT = 88

type VirtualPoolCourseListProps = {
  courses: ElectivePoolCourse[]
  completedNumbers: Set<string>
  countedLabel: string
  requiredLabel?: string
  requiredCurriculumNumbers?: Set<string>
  compact?: boolean
  showChainLayout?: boolean
  locale?: Locale
}

export function VirtualPoolCourseList({
  courses,
  completedNumbers,
  countedLabel,
  requiredLabel,
  requiredCurriculumNumbers,
  compact = false,
  showChainLayout = false,
  locale = 'en',
}: VirtualPoolCourseListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const itemHeight = showChainLayout
    ? CHAIN_ROW_HEIGHT
    : compact
      ? COMPACT_ROW_HEIGHT
      : REGULAR_ROW_HEIGHT

  const { virtualItems, totalHeight, offsetY } = useVirtualList({
    items: courses,
    itemHeight,
    scrollElementRef: scrollRef,
  })

  return (
    <div
      ref={scrollRef}
      className="mt-3 max-h-[min(52vh,28rem)] overflow-y-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/20 p-2"
      data-testid="virtual-pool-course-list"
    >
      <div role="list" className="relative" style={{ height: totalHeight }}>
        <div
          className={cn('absolute inset-x-0', showChainLayout ? 'space-y-0' : 'space-y-2')}
          style={{ transform: `translateY(${offsetY}px)` }}
        >
          {virtualItems.map(({ item: course, index }) => (
            <PoolCourseListItem
              key={course.courseNumber}
              as="div"
              course={course}
              displayTitle={localizedCourseTitle(course, locale)}
              isCounted={completedNumbers.has(course.courseNumber)}
              isRequiredCurriculum={requiredCurriculumNumbers?.has(course.courseNumber) ?? false}
              countedLabel={countedLabel}
              requiredLabel={requiredLabel}
              showChainStep={showChainLayout}
              stepNumber={index + 1}
              showConnector={showChainLayout && index < courses.length - 1}
              compact={compact && !showChainLayout}
            />
          ))}
        </div>
      </div>
    </div>
  )
}
