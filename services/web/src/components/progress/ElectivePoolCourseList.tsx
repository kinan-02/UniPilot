import { useDeferredValue, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Search } from 'lucide-react'
import { hasStructuredChainLayout } from '../../lib/chainRequirementSteps'
import {
  buildCourseEquivalenceGroups,
  expandNumbersWithEquivalence,
  isCountedViaEquivalence,
} from '../../lib/courseEquivalence'
import {
  catalogLinkForPool,
  countDedupedPoolCourses,
  interpolateTemplate,
  isChainPool,
  isRequiredCurriculumCourse,
  localizedCourseTitle,
  poolCourseFilterCounts,
  poolCountedCourseNumbers,
  preparePoolCourseView,
  VIRTUAL_LIST_THRESHOLD,
} from '../../lib/electivePools'
import { useTranslation } from '../../i18n'
import { ChainRequirementView } from './ChainRequirementView'
import { PoolCourseListItem } from './PoolCourseListItem'
import { VirtualPoolCourseList } from './VirtualPoolCourseList'
import { cn } from '../../lib/utils'
import type { CurriculumGraph, ElectiveBucket, GraduationProgress, RequirementProgressEntry } from '../../types/api'
import type { PoolCourseFilter } from '../../lib/electivePools'

type ElectivePoolCourseListProps = {
  pool: ElectiveBucket
  allPools: ElectiveBucket[]
  bucket: RequirementProgressEntry
  transcriptNumbers: Set<string>
  requiredCurriculumNumbers: Set<string>
  curriculumGraph?: CurriculumGraph | null
  graduationProgress?: GraduationProgress | null
  t: (key: string) => string
}

export function ElectivePoolCourseList({
  pool,
  allPools,
  bucket,
  transcriptNumbers: _transcriptNumbers,
  requiredCurriculumNumbers,
  curriculumGraph,
  graduationProgress,
  t,
}: ElectivePoolCourseListProps) {
  const { locale } = useTranslation()
  const [searchQuery, setSearchQuery] = useState('')
  const deferredSearch = useDeferredValue(searchQuery.trim().toLowerCase())

  const countedNumbers = useMemo(
    () => poolCountedCourseNumbers(pool, bucket, allPools),
    [allPools, bucket, pool],
  )

  const filterCounts = useMemo(
    () =>
      poolCourseFilterCounts(pool.courses, countedNumbers, {
        curriculumGraph,
        graduationProgress,
        requiredCurriculumNumbers,
      }),
    [countedNumbers, curriculumGraph, graduationProgress, pool.courses, requiredCurriculumNumbers],
  )

  const defaultCourseFilter = useMemo((): PoolCourseFilter => {
    if (filterCounts.remaining > 0 && filterCounts.counted > 0) return 'remaining'
    if (filterCounts.counted > 0) return 'counted'
    return 'all'
  }, [filterCounts.counted, filterCounts.remaining])

  const [courseFilter, setCourseFilter] = useState<PoolCourseFilter>(defaultCourseFilter)

  useEffect(() => {
    setCourseFilter(defaultCourseFilter)
  }, [defaultCourseFilter, pool.groupId])

  const useChainRequirementView = isChainPool(pool) && hasStructuredChainLayout(pool)

  const showChainLayout = isChainPool(pool) && pool.courses.length > 0 && !useChainRequirementView
  const useVirtualList = !showChainLayout && !useChainRequirementView && pool.courses.length >= VIRTUAL_LIST_THRESHOLD

  const equivalenceGroups = useMemo(
    () =>
      buildCourseEquivalenceGroups({
        curriculumGraph,
        progress: graduationProgress,
        poolCourses: pool.courses,
      }),
    [curriculumGraph, graduationProgress, pool.courses],
  )

  const expandedCountedNumbers = useMemo(
    () => expandNumbersWithEquivalence(countedNumbers, equivalenceGroups),
    [countedNumbers, equivalenceGroups],
  )

  const visibleCourses = useMemo(
    () =>
      preparePoolCourseView(pool.courses, {
        query: deferredSearch,
        completedNumbers: countedNumbers,
        filter: courseFilter,
        sort: courseFilter === 'counted' ? 'counted_first' : 'catalog',
        curriculumGraph,
        graduationProgress,
        requiredCurriculumNumbers,
      }),
    [
      countedNumbers,
      courseFilter,
      curriculumGraph,
      graduationProgress,
      deferredSearch,
      pool.courses,
      requiredCurriculumNumbers,
    ],
  )

  const dedupedCourseCount = useMemo(
    () =>
      countDedupedPoolCourses(pool.courses, {
        countedNumbers,
        requiredCurriculumNumbers,
        curriculumGraph,
        progress: graduationProgress,
      }),
    [countedNumbers, curriculumGraph, graduationProgress, pool.courses, requiredCurriculumNumbers],
  )

  if (useChainRequirementView) {
    return (
      <div data-testid={`elective-pool-detail-${pool.groupId}`}>
        <ChainRequirementView
          pool={pool}
          allPools={allPools}
          bucket={bucket}
          requiredCurriculumNumbers={requiredCurriculumNumbers}
          curriculumGraph={curriculumGraph}
          t={t}
        />
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid={`elective-pool-detail-${pool.groupId}`}>
      <label className="relative block">
        <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={t('progress.electiveExplorer.searchCourses')}
          className="h-10 w-full rounded-lg border border-[var(--color-border)] bg-white ps-9 pe-3 text-sm outline-none focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/15"
        />
      </label>

      <div className="flex flex-wrap gap-2" role="group" aria-label={t('progress.electiveExplorer.courseFilterLabel')}>
        {(['all', 'counted', 'remaining'] as const).map((filterKey) => (
          <button
            key={filterKey}
            type="button"
            aria-pressed={courseFilter === filterKey}
            onClick={() => setCourseFilter(filterKey)}
            className={cn(
              'rounded-full border px-3 py-1 text-xs font-medium transition',
              courseFilter === filterKey
                ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                : 'border-[var(--color-border)] bg-white text-[var(--color-text-muted)] hover:bg-[var(--color-surface-muted)]',
            )}
          >
            {t(`progress.electiveExplorer.courseFilters.${filterKey}`)} ({filterCounts[filterKey]})
          </button>
        ))}
      </div>

      <p className="text-xs text-[var(--color-text-muted)]">
        {interpolateTemplate(t('progress.electiveExplorer.showingCourses'), {
          shown: visibleCourses.length,
          total: dedupedCourseCount,
        })}
      </p>

      {pool.courses.length ? (
        visibleCourses.length ? (
          useVirtualList ? (
            <VirtualPoolCourseList
              courses={visibleCourses}
              completedNumbers={expandedCountedNumbers}
              requiredCurriculumNumbers={requiredCurriculumNumbers}
              countedLabel={t('progress.electiveExplorer.counted')}
              requiredLabel={t('progress.electiveExplorer.requiredCourse')}
              compact
              locale={locale}
            />
          ) : (
            <ul className={cn(showChainLayout ? 'space-y-0' : 'space-y-2')}>
              {visibleCourses.map((course, index) => (
                <PoolCourseListItem
                  key={course.courseNumber}
                  course={course}
                  displayTitle={localizedCourseTitle(course, locale)}
                  isCounted={isCountedViaEquivalence(
                    course.courseNumber,
                    countedNumbers,
                    equivalenceGroups,
                  )}
                  isRequiredCurriculum={isRequiredCurriculumCourse(
                    course.courseNumber,
                    requiredCurriculumNumbers,
                  )}
                  countedLabel={t('progress.electiveExplorer.counted')}
                  requiredLabel={t('progress.electiveExplorer.requiredCourse')}
                  showChainStep={showChainLayout}
                  stepNumber={index + 1}
                  showConnector={showChainLayout && index < visibleCourses.length - 1}
                  compact={!showChainLayout}
                />
              ))}
            </ul>
          )
        ) : (
          <p className="rounded-lg border border-dashed border-[var(--color-border)] px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">
            {t('progress.electiveExplorer.noCoursesMatch')}
          </p>
        )
      ) : (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] px-4 py-6 text-center text-sm text-[var(--color-text-muted)]">
          {t('progress.electiveExplorer.emptyCourseList')}
        </p>
      )}

      <div className="flex justify-end pt-1">
        <Link
          to={catalogLinkForPool(pool)}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 text-sm font-medium hover:bg-[var(--color-surface-muted)]"
        >
          <BookOpen className="h-4 w-4" />
          {t('progress.electiveExplorer.openCatalog')}
        </Link>
      </div>
    </div>
  )
}
