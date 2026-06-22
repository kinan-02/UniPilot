import { useDeferredValue, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { Card } from '../ui/Card'
import { interpolateTemplate } from '../../lib/electivePools'
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

  const explorerPools = useMemo(
    () => pools.filter((pool) => pool.explorerReady),
    [pools],
  )

  const filteredPools = useMemo(() => {
    if (!deferredSearch) return explorerPools
    return explorerPools.filter((pool) => {
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
    })
  }, [deferredSearch, explorerPools])

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

      {filteredPools.length ? (
        <ul className="space-y-2">
          {filteredPools.map((pool) => (
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
