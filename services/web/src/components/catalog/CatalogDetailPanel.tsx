import { Link } from 'react-router-dom'
import { CalendarPlus, Copy, TrendingUp, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { catalogApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import { courseTitle } from '../../lib/planning'
import { Button } from '../ui/Button'
import { Card, Spinner } from '../ui/Card'
import { CourseDetailBody } from './CourseDetailBody'
import type { CourseSummary } from '../../types/api'

type CatalogDetailPanelProps = {
  course: CourseSummary
  onClose: () => void
}

export function CatalogDetailPanel({ course, onClose }: CatalogDetailPanelProps) {
  const { t, locale } = useTranslation()

  const detailQuery = useQuery({
    queryKey: ['catalog-course-detail', course.courseNumber],
    queryFn: () => catalogApi.course(course.courseNumber, true),
    staleTime: 60_000,
  })

  const detail = detailQuery.data?.course

  const copyCourseNumber = async () => {
    try {
      await navigator.clipboard.writeText(course.courseNumber)
    } catch {
      // Clipboard unavailable — ignore silently.
    }
  }

  return (
    <Card
      className="max-h-[calc(100vh-6rem)] overflow-y-auto lg:sticky lg:top-8"
      data-testid="catalog-detail-panel"
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-sm text-[var(--color-primary)]">{course.courseNumber}</p>
            <button
              type="button"
              onClick={copyCourseNumber}
              className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"
              aria-label={t('catalog.copyCourseNumber')}
            >
              <Copy className="h-3 w-3" />
              {t('catalog.copyCourseNumber')}
            </button>
          </div>
          <h2 className="text-lg font-semibold leading-snug">{courseTitle(course, locale)}</h2>
          {course.faculty ? (
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">{course.faculty}</p>
          ) : null}
        </div>
        <button
          type="button"
          className="rounded-lg p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"
          onClick={onClose}
          aria-label={t('common.close')}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="mb-4 flex flex-wrap gap-2">
        <Link
          to="/plans/new"
          className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
        >
          <CalendarPlus className="h-4 w-4 text-[var(--color-primary)]" />
          {t('catalog.addToPlan')}
        </Link>
        <Link
          to="/progress"
          className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
        >
          <TrendingUp className="h-4 w-4 text-[var(--color-primary)]" />
          {t('catalog.viewProgress')}
        </Link>
        <Link
          to="/transcript"
          className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
        >
          {t('progress.updateTranscript')}
        </Link>
      </div>

      {detailQuery.isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      ) : detailQuery.isError || !detail ? (
        <div className="space-y-3">
          <p className="text-sm text-[var(--color-danger)]">{t('catalog.detailLoadFailed')}</p>
          <Button variant="secondary" size="sm" onClick={() => detailQuery.refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      ) : (
        <CourseDetailBody course={detail} />
      )}
    </Card>
  )
}
