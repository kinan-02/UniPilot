import { useDeferredValue, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { Card } from '../ui/Card'
import {
  filterPoolsByExclusiveChainSelection,
  groupExclusiveChainPools,
} from '../../lib/electiveChainVisibility'
import { interpolateTemplate, partitionExplorerPools } from '../../lib/electivePools'
import { ElectivePoolRow } from './ElectivePoolRow'
import type { CurriculumGraph, ElectiveBucket, RequirementProgressEntry } from '../../types/api'

function PoolCourseLegendSwatch({
  borderClass,
  bgClass,
  label,
}: {
  borderClass: string
  bgClass: string
  label: string
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
      <span
        className={`h-3.5 w-3.5 shrink-0 rounded border ${borderClass} ${bgClass}`}
        aria-hidden
      />
      {label}
    </span>
  )
}

type ElectivePoolsPanelProps = {
  pools: ElectiveBucket[]
  requirementBuckets: RequirementProgressEntry[]
  requiredCurriculumNumbers: Set<string>
  transcriptNumbers: Set<string>
  curriculumGraph?: CurriculumGraph | null
  expandedPoolId: string | null
  t: (key: string) => string
  onExpandedPoolChange: (bucket: RequirementProgressEntry, pool: ElectiveBucket | null) => void
}

export function ElectivePoolsPanel({
  pools,
  requirementBuckets,
  requiredCurriculumNumbers,
  transcriptNumbers,
  curriculumGraph,
  expandedPoolId,
  t,
  onExpandedPoolChange,
}: ElectivePoolsPanelProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [showAllChainOptions, setShowAllChainOptions] = useState(false)
  const deferredSearch = useDeferredValue(searchQuery.trim().toLowerCase())

  const { programPools, generalTechnionPools } = useMemo(
    () => partitionExplorerPools(pools),
    [pools],
  )

  const chainSelection = useMemo(
    () =>
      filterPoolsByExclusiveChainSelection(
        programPools,
        requirementBuckets,
        transcriptNumbers,
        t,
        {
          showAllChainOptions: showAllChainOptions || Boolean(deferredSearch),
          curriculumGraph,
        },
      ),
    [
      deferredSearch,
      programPools,
      requirementBuckets,
      showAllChainOptions,
      curriculumGraph,
      t,
      transcriptNumbers,
    ],
  )

  const visibleProgramPools = chainSelection.pools
  const hiddenExclusiveChainCount = chainSelection.hiddenExclusiveChainCount
  const hasExclusiveChainGroups = useMemo(
    () => [...groupExclusiveChainPools(programPools).values()].some((group) => group.length >= 2),
    [programPools],
  )

  const explorerPools = useMemo(
    () => [...visibleProgramPools, ...generalTechnionPools],
    [generalTechnionPools, visibleProgramPools],
  )

  const filterPools = useMemo(() => {
    const matchesSearch = (pool: ElectiveBucket) => {
      if (!deferredSearch) return true
      const haystack = [
        pool.title ?? '',
        pool.groupId,
        pool.rule.operator ?? '',
        pool.rule.chain ?? '',
        ...(pool.allowedPrefixes ?? []),
        ...(pool.notes ?? []),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(deferredSearch)
    }
    return (list: ElectiveBucket[]) => list.filter(matchesSearch)
  }, [deferredSearch])

  const filteredProgramPools = useMemo(
    () => filterPools(visibleProgramPools),
    [filterPools, visibleProgramPools],
  )
  const filteredGeneralTechnionPools = useMemo(
    () => filterPools(generalTechnionPools),
    [filterPools, generalTechnionPools],
  )

  if (!explorerPools.length) return null

  const handleToggle = (bucket: RequirementProgressEntry, pool: ElectiveBucket) => {
    onExpandedPoolChange(bucket, expandedPoolId === pool.groupId ? null : pool)
  }

  return (
    <Card className="space-y-4" data-testid="elective-pools-panel" id="elective-pools-panel">
      <div>
        <h2 className="text-lg font-semibold">{t('progress.electiveExplorer.catalogTitle')}</h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          {t('progress.electiveExplorer.catalogHintSimple')}
        </p>
      </div>

      <label className="relative block">
        <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
        <input
          type="search"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder={t('progress.electiveExplorer.searchPools')}
          className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white ps-9 pe-3 text-sm outline-none focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/15"
        />
      </label>

      <div
        className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-4 py-2.5"
        data-testid="elective-pools-legend"
      >
        <span className="text-xs font-medium text-[var(--color-text-muted)]">
          {t('progress.electiveExplorer.courseLegendTitle')}
        </span>
        <PoolCourseLegendSwatch
          borderClass="border-emerald-200"
          bgClass="bg-emerald-50"
          label={t('progress.electiveExplorer.legendCounted')}
        />
        <PoolCourseLegendSwatch
          borderClass="border-sky-200"
          bgClass="bg-sky-50"
          label={t('progress.electiveExplorer.legendRequired')}
        />
        <PoolCourseLegendSwatch
          borderClass="border-[var(--color-border)]"
          bgClass="bg-white"
          label={t('progress.electiveExplorer.legendElective')}
        />
      </div>

      {hiddenExclusiveChainCount > 0 && !showAllChainOptions && !deferredSearch ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-violet-200 bg-violet-50/70 px-4 py-3">
          <p className="text-sm text-violet-950">
            {interpolateTemplate(t('progress.electiveExplorer.hiddenChainOptions'), {
              count: hiddenExclusiveChainCount,
            })}
          </p>
          <button
            type="button"
            onClick={() => setShowAllChainOptions(true)}
            className="shrink-0 rounded-lg border border-violet-300 bg-white px-3 py-1.5 text-sm font-medium text-violet-900 transition hover:bg-violet-100"
          >
            {t('progress.electiveExplorer.showAllChainOptions')}
          </button>
        </div>
      ) : null}

      {showAllChainOptions && hasExclusiveChainGroups && !deferredSearch ? (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => setShowAllChainOptions(false)}
            className="text-sm font-medium text-[var(--color-primary)] hover:underline"
          >
            {t('progress.electiveExplorer.hideUnselectedChains')}
          </button>
        </div>
      ) : null}

      {filteredProgramPools.length || filteredGeneralTechnionPools.length ? (
        <div className="space-y-6">
          {filteredProgramPools.length ? (
            <ul className="space-y-2">
              {filteredProgramPools.map((pool) => (
                <li key={pool.groupId}>
                  <ElectivePoolRow
                    pool={pool}
                    allPools={pools}
                    requirementBuckets={requirementBuckets}
                    requiredCurriculumNumbers={requiredCurriculumNumbers}
                    transcriptNumbers={transcriptNumbers}
                    curriculumGraph={curriculumGraph}
                    expanded={expandedPoolId === pool.groupId}
                    t={t}
                    onToggle={handleToggle}
                  />
                </li>
              ))}
            </ul>
          ) : null}

          {generalTechnionPools.length && filteredGeneralTechnionPools.length ? (
            <section className="space-y-3 border-t border-[var(--color-border)] pt-5">
              <div>
                <h3 className="text-sm font-semibold">
                  {t('progress.electiveExplorer.generalTechnionPoolsTitle')}
                </h3>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                  {t('progress.electiveExplorer.generalTechnionPoolsHint')}
                </p>
              </div>
              <ul className="space-y-2">
                {filteredGeneralTechnionPools.map((pool) => (
                  <li key={pool.groupId}>
                    <ElectivePoolRow
                      pool={pool}
                      allPools={pools}
                      requirementBuckets={requirementBuckets}
                      requiredCurriculumNumbers={requiredCurriculumNumbers}
                      transcriptNumbers={transcriptNumbers}
                      curriculumGraph={curriculumGraph}
                      expanded={expandedPoolId === pool.groupId}
                      t={t}
                      onToggle={handleToggle}
                    />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
          {interpolateTemplate(t('progress.electiveExplorer.noPoolsMatch'), {
            query: searchQuery.trim(),
          })}
        </p>
      )}
    </Card>
  )
}
