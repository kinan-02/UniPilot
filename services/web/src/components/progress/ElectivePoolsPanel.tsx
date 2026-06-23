import { useDeferredValue, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { Card } from '../ui/Card'
import { interpolateTemplate, partitionExplorerPools } from '../../lib/electivePools'
import { ElectivePoolRow } from './ElectivePoolRow'
import type { ElectiveBucket, RequirementProgressEntry } from '../../types/api'

type ElectivePoolsPanelProps = {
  pools: ElectiveBucket[]
  requirementBuckets: RequirementProgressEntry[]
  requiredCurriculumNumbers: Set<string>
  transcriptNumbers: Set<string>
  expandedPoolId: string | null
  t: (key: string) => string
  onExpandedPoolChange: (bucket: RequirementProgressEntry, pool: ElectiveBucket | null) => void
}

export function ElectivePoolsPanel({
  pools,
  requirementBuckets,
  requiredCurriculumNumbers,
  transcriptNumbers,
  expandedPoolId,
  t,
  onExpandedPoolChange,
}: ElectivePoolsPanelProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const deferredSearch = useDeferredValue(searchQuery.trim().toLowerCase())

  const { programPools, generalTechnionPools } = useMemo(
    () => partitionExplorerPools(pools),
    [pools],
  )
  const explorerPools = useMemo(
    () => [...programPools, ...generalTechnionPools],
    [generalTechnionPools, programPools],
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
    () => filterPools(programPools),
    [filterPools, programPools],
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

      {filteredProgramPools.length || filteredGeneralTechnionPools.length ? (
        <div className="space-y-6">
          {filteredProgramPools.length ? (
            <ul className="space-y-2">
              {filteredProgramPools.map((pool) => (
                <li key={pool.groupId}>
                  <ElectivePoolRow
                    pool={pool}
                    allPools={explorerPools}
                    requirementBuckets={requirementBuckets}
                    requiredCurriculumNumbers={requiredCurriculumNumbers}
                    transcriptNumbers={transcriptNumbers}
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
                      allPools={explorerPools}
                      requirementBuckets={requirementBuckets}
                      requiredCurriculumNumbers={requiredCurriculumNumbers}
                      transcriptNumbers={transcriptNumbers}
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
