import { useDeferredValue, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, Search } from 'lucide-react'
import { hasStructuredChainLayout } from '../../lib/chainRequirementSteps'
import {
  catalogLinkForPool,
  interpolateTemplate,
  isChainPool,
  localizedCourseTitle,
  poolCountedCourseNumbers,
  preparePoolCourseView,
  VIRTUAL_LIST_THRESHOLD,
} from '../../lib/electivePools'
import { useTranslation } from '../../i18n'
import { ChainRequirementView } from './ChainRequirementView'
import { PoolCourseListItem } from './PoolCourseListItem'
import { VirtualPoolCourseList } from './VirtualPoolCourseList'
import { cn } from '../../lib/utils'
import type { ElectiveBucket, RequirementProgressEntry } from '../../types/api'

type ElectivePoolCourseListProps = {
  pool: ElectiveBucket
  bucket: RequirementProgressEntry
  transcriptNumbers: Set<string>
  requiredCurriculumNumbers: Set<string>
  t: (key: string) => string
}

export function ElectivePoolCourseList({
  pool,
  bucket,
  transcriptNumbers,
  requiredCurriculumNumbers,
  t,
}: ElectivePoolCourseListProps) {
  const { locale } = useTranslation()
  const [searchQuery, setSearchQuery] = useState('')
  const deferredSearch = useDeferredValue(searchQuery.trim().toLowerCase())

  const countedNumbers = useMemo(
    () => poolCountedCourseNumbers(pool, bucket, transcriptNumbers),
    [bucket, pool, transcriptNumbers],
  )

  const useChainRequirementView = isChainPool(pool) && hasStructuredChainLayout(pool)

  const showChainLayout = isChainPool(pool) && pool.courses.length > 0 && !useChainRequirementView
  const useVirtualList = !showChainLayout && !useChainRequirementView && pool.courses.length >= VIRTUAL_LIST_THRESHOLD

  const visibleCourses = useMemo(
    () =>
      preparePoolCourseView(pool.courses, {
        query: deferredSearch,
        completedNumbers: countedNumbers,
        filter: 'all',
        sort: 'catalog',
      }),
    [countedNumbers, deferredSearch, pool.courses],
  )

  if (useChainRequirementView) {
    return (
      <div data-testid={`elective-pool-detail-${pool.groupId}`}>
        <ChainRequirementView
          pool={pool}
          bucket={bucket}
          transcriptNumbers={transcriptNumbers}
          requiredCurriculumNumbers={requiredCurriculumNumbers}
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

      <p className="text-xs text-[var(--color-text-muted)]">
        {interpolateTemplate(t('progress.electiveExplorer.showingCourses'), {
          shown: visibleCourses.length,
          total: pool.courses.length,
        })}
      </p>

      {pool.courses.length ? (
        visibleCourses.length ? (
          useVirtualList ? (
            <VirtualPoolCourseList
              courses={visibleCourses}
              completedNumbers={countedNumbers}
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
                  isCounted={countedNumbers.has(course.courseNumber)}
                  isRequiredCurriculum={requiredCurriculumNumbers.has(course.courseNumber)}
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
