import { Link } from 'react-router-dom'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { catalogApi } from '../api/endpoints'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useCatalogCourses } from '../hooks/useCatalogCourses'
import { useCatalogRecentSearches } from '../hooks/useCatalogRecentSearches'
import { useMinWidth } from '../hooks/useMinWidth'
import { useTranslation } from '../i18n'
import {
  buildCatalogSearchParams,
  creditBandRange,
  parseCatalogSearchParams,
  type CatalogCreditBand,
} from '../lib/catalog'
import { CatalogCourseList } from '../components/catalog/CatalogCourseList'
import { CatalogDetailPanel } from '../components/catalog/CatalogDetailPanel'
import { CatalogPageSkeleton } from '../components/catalog/CatalogPageSkeleton'
import { CatalogSearchBar } from '../components/catalog/CatalogSearchBar'
import { CatalogStatsBar } from '../components/catalog/CatalogQuickFilters'
import { CourseDetailModal } from '../components/plans/CourseDetailModal'
import { Card, EmptyState, PageHeader } from '../components/ui/Card'
import type { CourseSummary } from '../types/api'

const DESKTOP_BREAKPOINT = 1024

export function CatalogPage() {
  const { t, locale } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
  const isDesktop = useMinWidth(DESKTOP_BREAKPOINT)
  const { recent, remember, clear: clearRecent } = useCatalogRecentSearches()

  const initial = parseCatalogSearchParams(searchParams)
  const [query, setQuery] = useState(initial.query)
  const [faculty, setFaculty] = useState(initial.faculty)
  const [creditBand, setCreditBand] = useState<CatalogCreditBand>(initial.creditBand)
  const [selected, setSelected] = useState<CourseSummary | null>(null)
  const debouncedQuery = useDebouncedValue(query.trim(), 350)
  const creditRange = creditBandRange(creditBand)

  const facultiesQuery = useQuery({
    queryKey: ['catalog-faculties'],
    queryFn: catalogApi.faculties,
    staleTime: 5 * 60 * 1000,
  })

  const coursesQuery = useCatalogCourses({
    query: debouncedQuery,
    faculty,
    minCredits: creditRange.minCredits,
    maxCredits: creditRange.maxCredits,
  })

  const courseFromUrl = searchParams.get('course')?.trim() ?? ''
  const deepLinkQuery = useQuery({
    queryKey: ['catalog-course-prefetch', courseFromUrl],
    queryFn: () => catalogApi.course(courseFromUrl, false),
    enabled: Boolean(courseFromUrl) && !selected,
  })

  useEffect(() => {
    const parsed = parseCatalogSearchParams(searchParams)
    setQuery((current) => (current === parsed.query ? current : parsed.query))
    setFaculty((current) => (current === parsed.faculty ? current : parsed.faculty))
    setCreditBand((current) => (current === parsed.creditBand ? current : parsed.creditBand))
  }, [searchParams])

  useEffect(() => {
    const params = buildCatalogSearchParams({
      query: debouncedQuery,
      faculty,
      creditBand,
      courseNumber: selected?.courseNumber,
    })
    setSearchParams(params, { replace: true })
  }, [debouncedQuery, faculty, creditBand, selected?.courseNumber, setSearchParams])

  useEffect(() => {
    if (!courseFromUrl || selected) return
    const course = deepLinkQuery.data?.course
    if (course) setSelected(course)
  }, [courseFromUrl, deepLinkQuery.data?.course, selected])

  useEffect(() => {
    if (debouncedQuery.length >= 2) remember(debouncedQuery)
  }, [debouncedQuery, remember])

  useEffect(() => {
    if (selected || !/^0\d{7}$/.test(debouncedQuery)) return
    const match = coursesQuery.items.find((course) => course.courseNumber === debouncedQuery)
    if (match) setSelected(match)
  }, [coursesQuery.items, debouncedQuery, selected])

  const faculties = facultiesQuery.data?.items ?? []

  const handleQueryChange = useCallback((value: string) => {
    setQuery(value)
    setSelected(null)
  }, [])

  const handleFacultyChange = useCallback((value: string) => {
    setFaculty(value)
    setSelected(null)
  }, [])

  const handleCreditBandChange = useCallback((band: CatalogCreditBand) => {
    setCreditBand(band)
    setSelected(null)
  }, [])

  const handleClearFilters = useCallback(() => {
    setQuery('')
    setFaculty('')
    setCreditBand('all')
    setSelected(null)
  }, [])

  const handleSelectCourse = useCallback((course: CourseSummary) => {
    setSelected(course)
  }, [])

  const handleCloseDetail = useCallback(() => {
    setSelected(null)
  }, [])

  const initialLoading = coursesQuery.isLoading && !coursesQuery.data

  const emptySelectionHint = useMemo(
    () => (
      <Card className="hidden h-fit border-dashed lg:block lg:sticky lg:top-8" data-testid="catalog-detail-placeholder">
        <p className="text-sm font-medium">{t('catalog.selectCourseTitle')}</p>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">{t('catalog.selectCourseHint')}</p>
      </Card>
    ),
    [t],
  )

  if (initialLoading) {
    return (
      <div className="animate-fade-in">
        <PageHeader title={t('catalog.title')} description={t('catalog.subtitle')} />
        <CatalogPageSkeleton />
      </div>
    )
  }

  return (
    <div className="animate-fade-in">
      <PageHeader title={t('catalog.title')} description={t('catalog.subtitle')} />

      <CatalogSearchBar
        query={query}
        faculty={faculty}
        creditBand={creditBand}
        faculties={faculties}
        facultiesLoading={facultiesQuery.isLoading}
        recentSearches={recent}
        t={t}
        onQueryChange={handleQueryChange}
        onFacultyChange={handleFacultyChange}
        onCreditBandChange={handleCreditBandChange}
        onRecentSelect={handleQueryChange}
        onClearRecent={clearRecent}
        onClear={handleClearFilters}
      />

      {facultiesQuery.isError ? (
        <Card className="mb-4 border-amber-200 bg-amber-50/60 px-4 py-3 text-sm text-amber-900">
          {t('catalog.facultiesLoadFailed')}
        </Card>
      ) : null}

      <CatalogStatsBar
        total={coursesQuery.total}
        visible={coursesQuery.items.length}
        isFetching={coursesQuery.isFetching && !coursesQuery.isFetchingNextPage}
        t={t}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_400px]">
        <CatalogCourseList
          items={coursesQuery.items}
          total={coursesQuery.total}
          selectedCourseNumber={selected?.courseNumber}
          isLoading={coursesQuery.isLoading}
          isFetching={coursesQuery.isFetching}
          isFetchingNextPage={coursesQuery.isFetchingNextPage}
          isError={coursesQuery.isError}
          hasMore={coursesQuery.hasMore}
          locale={locale}
          t={t}
          onSelect={handleSelectCourse}
          onLoadMore={coursesQuery.loadMore}
          onRetry={() => coursesQuery.refetch()}
        />

        {selected && isDesktop ? (
          <CatalogDetailPanel course={selected} onClose={handleCloseDetail} />
        ) : (
          emptySelectionHint
        )}
      </div>

      {selected && !isDesktop ? (
        <CourseDetailModal courseNumber={selected.courseNumber} onClose={handleCloseDetail} />
      ) : null}

      {!selected && courseFromUrl && deepLinkQuery.isError ? (
        <EmptyState
          title={t('catalog.courseNotFound')}
          description={t('catalog.courseNotFoundHint')}
          action={
            <Link to="/catalog" className="text-sm font-medium text-[var(--color-primary)]">
              {t('catalog.clearFilters')}
            </Link>
          }
        />
      ) : null}
    </div>
  )
}
