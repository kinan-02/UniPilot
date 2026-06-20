import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { catalogApi } from '../api/endpoints'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useTranslation } from '../i18n'
import { courseTitle } from '../lib/planning'
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import { formatCredits } from '../lib/utils'
import type { CourseSummary } from '../types/api'

const PAGE_SIZE = 30

export function CatalogPage() {
  const { t, locale } = useTranslation()
  const [query, setQuery] = useState('')
  const [faculty, setFaculty] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<CourseSummary | null>(null)
  const debouncedQuery = useDebouncedValue(query.trim(), 350)

  const coursesQuery = useQuery({
    queryKey: ['catalog-courses', debouncedQuery, faculty, offset],
    queryFn: () => {
      const params: Record<string, string | number | boolean> = {
        limit: PAGE_SIZE,
        offset,
      }
      if (debouncedQuery) params.q = debouncedQuery
      if (faculty) params.faculty = faculty
      return catalogApi.courses(params)
    },
  })

  const detailQuery = useQuery({
    queryKey: ['catalog-course-detail', selected?.courseNumber],
    queryFn: () => catalogApi.course(selected!.courseNumber, true),
    enabled: Boolean(selected?.courseNumber),
  })

  const items = coursesQuery.data?.items ?? []
  const total = coursesQuery.data?.total ?? 0

  const faculties = useMemo(() => {
    const set = new Set<string>()
    items.forEach((course) => {
      if (course.faculty) set.add(course.faculty)
    })
    return Array.from(set).sort()
  }, [items])

  const handleSearchChange = (value: string) => {
    setQuery(value)
    setOffset(0)
  }

  return (
    <div className="animate-fade-in">
      <PageHeader title={t('catalog.title')} description={t('catalog.subtitle')} />

      <Card className="mb-6">
        <div className="grid gap-4 lg:grid-cols-[1fr_220px]">
          <div className="relative">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <Input
              className="ps-10"
              placeholder={t('catalog.searchPlaceholder')}
              value={query}
              onChange={(e) => handleSearchChange(e.target.value)}
            />
          </div>
          <label className="block space-y-1.5">
            <span className="text-sm font-medium">{t('catalog.faculty')}</span>
            <select
              value={faculty}
              onChange={(e) => {
                setFaculty(e.target.value)
                setOffset(0)
              }}
              className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3.5 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
            >
              <option value="">{t('catalog.allFaculties')}</option>
              {faculties.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
        </div>
        <p className="mt-3 text-xs text-[var(--color-text-muted)]">{t('catalog.searchHint')}</p>
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div>
          {coursesQuery.isLoading ? (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          ) : items.length ? (
            <>
              <div className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft)]">
                <div className="divide-y divide-[var(--color-border)]">
                  {items.map((course) => (
                    <button
                      key={course.courseNumber}
                      type="button"
                      onClick={() => setSelected(course)}
                      className={`flex w-full flex-col gap-2 px-5 py-4 text-start transition hover:bg-[var(--color-surface-muted)] sm:flex-row sm:items-center sm:justify-between ${
                        selected?.courseNumber === course.courseNumber
                          ? 'bg-[var(--color-surface-muted)]'
                          : ''
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="font-mono text-sm font-medium text-[var(--color-primary)]">
                          {course.courseNumber}
                        </p>
                        <p className="truncate text-sm">{courseTitle(course, locale)}</p>
                        {course.faculty ? (
                          <p className="text-xs text-[var(--color-text-muted)]">{course.faculty}</p>
                        ) : null}
                      </div>
                      <div className="text-sm text-[var(--color-text-muted)]">
                        {formatCredits(course.credits)} {t('common.credits')}
                      </div>
                    </button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-[var(--color-border)] px-5 py-3">
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {t('catalog.showing')} {items.length + offset} {t('catalog.of')} {total}{' '}
                    {t('catalog.courses')}
                  </p>
                  {offset + PAGE_SIZE < total ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={coursesQuery.isFetching}
                      onClick={() => setOffset((value) => value + PAGE_SIZE)}
                    >
                      {t('catalog.loadMore')}
                    </Button>
                  ) : null}
                </div>
              </div>
            </>
          ) : (
            <EmptyState title={t('catalog.noCourses')} description={t('catalog.noCoursesHint')} />
          )}
        </div>

        <Card className="h-fit lg:sticky lg:top-8">
          {selected ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-mono text-sm text-[var(--color-primary)]">{selected.courseNumber}</p>
                  <h2 className="text-lg font-semibold">{courseTitle(selected, locale)}</h2>
                  {selected.faculty ? (
                    <p className="text-sm text-[var(--color-text-muted)]">{selected.faculty}</p>
                  ) : null}
                </div>
                <button
                  type="button"
                  className="rounded-lg p-1 text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]"
                  onClick={() => setSelected(null)}
                  aria-label={t('common.cancel')}
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <p className="text-sm">
                {formatCredits(selected.credits)} {t('common.credits')}
              </p>
              <div>
                <h3 className="mb-2 text-sm font-semibold">{t('catalog.offerings')}</h3>
                {detailQuery.isLoading ? (
                  <Spinner />
                ) : detailQuery.data?.course.offerings?.length ? (
                  <ul className="space-y-2 text-sm">
                    {detailQuery.data.course.offerings.map((offering, index) => (
                      <li
                        key={`${offering.academicYear}-${offering.semesterCode}-${index}`}
                        className="rounded-lg bg-[var(--color-surface-muted)] px-3 py-2"
                      >
                        <p className="font-medium">
                          {offering.academicYear} · {offering.semesterCode}
                        </p>
                        {(offering.scheduleGroups ?? []).slice(0, 3).map((group, groupIndex) => (
                          <p key={groupIndex} className="text-xs text-[var(--color-text-muted)]">
                            {(group.day ?? group['יום'] ?? '') as string}{' '}
                            {(group.time ?? group['שעה'] ?? '') as string}
                          </p>
                        ))}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-[var(--color-text-muted)]">{t('catalog.noOfferings')}</p>
                )}
              </div>
            </div>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">{t('catalog.viewDetails')}</p>
          )}
        </Card>
      </div>
    </div>
  )
}
