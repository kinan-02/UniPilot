import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { courseTitle } from '../../lib/planning'
import { formatCredits } from '../../lib/utils'
import { catalogApi } from '../../api/endpoints'
import { Button } from '../ui/Button'
import { EmptyState, Spinner } from '../ui/Card'
import type { CourseSummary } from '../../types/api'

type CatalogCourseListProps = {
  items: CourseSummary[]
  total: number
  selectedCourseNumber?: string | null
  isLoading: boolean
  isFetching: boolean
  isFetchingNextPage: boolean
  isError: boolean
  hasMore: boolean
  locale: 'he' | 'en'
  t: (key: string) => string
  onSelect: (course: CourseSummary) => void
  onLoadMore: () => void
  onRetry: () => void
}

export function CatalogCourseList({
  items,
  total,
  selectedCourseNumber,
  isLoading,
  isFetching,
  isFetchingNextPage,
  isError,
  hasMore,
  locale,
  t,
  onSelect,
  onLoadMore,
  onRetry,
}: CatalogCourseListProps) {
  const queryClient = useQueryClient()
  const selectedRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (selectedCourseNumber && selectedRef.current?.scrollIntoView) {
      selectedRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [selectedCourseNumber, items.length])

  const prefetchDetail = (courseNumber: string) => {
    void queryClient.prefetchQuery({
      queryKey: ['catalog-course-detail', courseNumber],
      queryFn: () => catalogApi.course(courseNumber, true),
      staleTime: 60_000,
    })
  }

  if (isLoading) {
    return (
      <div className="flex justify-center py-16" data-testid="catalog-course-list-loading">
        <Spinner />
      </div>
    )
  }

  if (isError) {
    return (
      <EmptyState
        title={t('catalog.loadFailed')}
        description={t('common.errorGeneric')}
        action={
          <Button variant="secondary" size="sm" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        }
      />
    )
  }

  if (!items.length) {
    return <EmptyState title={t('catalog.noCourses')} description={t('catalog.noCoursesHint')} />
  }

  const visibleCount = items.length

  return (
    <div
      className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft)]"
      data-testid="catalog-course-list"
    >
      <div className="divide-y divide-[var(--color-border)]">
        {items.map((course) => {
          const isSelected = selectedCourseNumber === course.courseNumber
          return (
            <button
              key={course.courseNumber}
              ref={isSelected ? selectedRef : undefined}
              type="button"
              data-testid={`catalog-course-row-${course.courseNumber}`}
              onClick={() => onSelect(course)}
              onMouseEnter={() => prefetchDetail(course.courseNumber)}
              onFocus={() => prefetchDetail(course.courseNumber)}
              className={`flex w-full flex-col gap-2 px-5 py-4 text-start transition hover:bg-[var(--color-surface-muted)] sm:flex-row sm:items-center sm:justify-between ${
                isSelected ? 'bg-[var(--color-surface-muted)] ring-1 ring-inset ring-[var(--color-primary)]/20' : ''
              }`}
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="font-mono text-sm font-medium text-[var(--color-primary)]">
                    {course.courseNumber}
                  </p>
                  {course.semesterOfferingSummary ? (
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
                      {t('catalog.offeredThisTerm')}
                    </span>
                  ) : null}
                </div>
                <p className="truncate text-sm">{courseTitle(course, locale)}</p>
                {course.faculty ? (
                  <p className="truncate text-xs text-[var(--color-text-muted)]">{course.faculty}</p>
                ) : null}
              </div>
              <div className="text-sm tabular-nums text-[var(--color-text-muted)]">
                {formatCredits(course.credits)} {t('common.credits')}
              </div>
            </button>
          )
        })}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-5 py-3">
        <p className="text-xs text-[var(--color-text-muted)]">
          {t('catalog.resultsSummary')
            .replace('{visible}', String(visibleCount))
            .replace('{total}', String(total))}
        </p>
        {hasMore ? (
          <Button
            variant="secondary"
            size="sm"
            loading={isFetchingNextPage}
            onClick={onLoadMore}
            disabled={isFetchingNextPage}
          >
            {t('catalog.loadMore')}
          </Button>
        ) : null}
      </div>
      {isFetching && !isFetchingNextPage ? (
        <div className="border-t border-[var(--color-border)] px-5 py-2 text-center text-xs text-[var(--color-text-muted)]">
          {t('catalog.updatingResults')}
        </div>
      ) : null}
    </div>
  )
}
