import { useState } from 'react'
import { Info, Plus, Sparkles } from 'lucide-react'
import type { CourseSummary } from '../../types/api'
import type { Locale } from '../../i18n/types'
import { useTranslation } from '../../i18n'
import { courseTitle } from '../../lib/planning'
import { formatSlotTypes } from '../../lib/planner'
import { cn, formatCredits } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Card'

type CourseSearchPanelProps = {
  locale: Locale
  searchMinLength: number
  debouncedSearch: string
  loading: boolean
  error: boolean
  items: CourseSummary[]
  selectedCourseNumbers: Set<string>
  maybeCourseNumbers: Set<string>
  onAdd: (course: CourseSummary) => void
  onAddMaybe: (course: CourseSummary) => void
  onInfo: (courseNumber: string) => void
  disabled?: boolean
  listClassName?: string
}

export function CourseSearchPanel({
  locale,
  searchMinLength,
  debouncedSearch,
  loading,
  error,
  items,
  selectedCourseNumbers,
  maybeCourseNumbers,
  onAdd,
  onAddMaybe,
  onInfo,
  disabled,
  listClassName = 'max-h-80 space-y-1.5 overflow-y-auto',
}: CourseSearchPanelProps) {
  const { t } = useTranslation()
  const [hoveredCourseNumber, setHoveredCourseNumber] = useState<string | null>(null)

  if (disabled) {
    return (
      <p className="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
        {t('planner.selectSemesterFirst')}
      </p>
    )
  }

  if (loading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner />
      </div>
    )
  }

  if (debouncedSearch.length < searchMinLength) {
    return <p className="text-sm text-[var(--color-text-muted)]">{t('plans.searchCourseHint')}</p>
  }

  if (error) {
    return <p className="text-sm text-[var(--color-danger)]">{t('common.errorGeneric')}</p>
  }

  if (!items.length) {
    return (
      <p className="rounded-xl border border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
        {t('planner.noCoursesSemester')}
      </p>
    )
  }

  return (
    <div className={listClassName}>
      {items.map((course) => {
        const alreadySelected = selectedCourseNumbers.has(course.courseNumber)
        const alreadyMaybe = maybeCourseNumbers.has(course.courseNumber)
        const inAnyList = alreadySelected || alreadyMaybe
        const isHovered = hoveredCourseNumber === course.courseNumber
        const title = courseTitle(course, locale)
        const meta = [
          course.faculty,
          course.credits != null ? formatCredits(course.credits) : null,
          course.semesterOfferingSummary?.slotTypes?.length
            ? formatSlotTypes(course.semesterOfferingSummary.slotTypes)
            : null,
        ]
          .filter(Boolean)
          .join(' · ')

        return (
          <div
            key={course.id ?? course.courseNumber}
            onMouseEnter={() => setHoveredCourseNumber(course.courseNumber)}
            onMouseLeave={() => setHoveredCourseNumber(null)}
            className={cn(
              'rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-2.5 py-2 transition',
              alreadySelected && 'opacity-70',
              isHovered && !inAnyList && 'border-[var(--color-primary)]/40 bg-white',
            )}
          >
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <p className="font-mono text-xs font-semibold text-[var(--color-primary)]">
                    {course.courseNumber}
                  </p>
                  {alreadySelected ? (
                    <span className="text-[10px] font-medium text-[var(--color-primary)]">
                      {t('planner.alreadySelected')}
                    </span>
                  ) : alreadyMaybe ? (
                    <span className="text-[10px] font-medium text-[var(--color-text-muted)]">
                      {t('planner.alreadyInMaybe')}
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-sm font-medium leading-snug text-[var(--color-text)]">{title}</p>
                {meta ? (
                  <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--color-text-muted)]">{meta}</p>
                ) : null}
              </div>

              <div className="flex shrink-0 items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="!h-8 !w-8 !p-0"
                  aria-label={t('planner.courseInfo')}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation()
                    onInfo(course.courseNumber)
                  }}
                >
                  <Info className="h-4 w-4" />
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  className="!h-8 !px-2"
                  disabled={inAnyList}
                  title={t('planner.addToMaybe')}
                  aria-label={t('planner.addToMaybe')}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation()
                    onAddMaybe(course)
                  }}
                >
                  <Sparkles className="h-4 w-4" />
                  <span className="hidden sm:inline">{t('planner.addToMaybe')}</span>
                </Button>
                <Button
                  type="button"
                  size="sm"
                  className="!h-8 !px-2.5"
                  disabled={inAnyList}
                  title={t('catalog.addToPlan')}
                  aria-label={t('catalog.addToPlan')}
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation()
                    onAdd(course)
                  }}
                >
                  <Plus className="h-4 w-4" />
                  <span className="hidden sm:inline">{t('catalog.addToPlan')}</span>
                </Button>
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}
