import { ChevronDown } from 'lucide-react'
import { hasStructuredChainLayout } from '../../lib/chainRequirementSteps'
import {
  interpolateTemplate,
  isChainPool,
  localizedPoolDescriptions,
  localizedPoolTitle,
  poolProgressSummary,
  progressBucketForPool,
  resolvePoolProgressDisplay,
  shouldShowPoolCatalogExplanation,
} from '../../lib/electivePools'
import { cn, formatCredits } from '../../lib/utils'
import { ElectivePoolCourseList } from './ElectivePoolCourseList'
import { PoolCatalogExplanation } from './PoolCatalogExplanation'
import { PoolProgressBadge, PoolProgressStrip } from './PoolProgressStrip'
import { PoolRuleBadge } from './PoolRuleBadge'
import type { CurriculumGraph, ElectiveBucket, RequirementProgressEntry } from '../../types/api'

type ElectivePoolRowProps = {
  pool: ElectiveBucket
  allPools: ElectiveBucket[]
  requirementBuckets: RequirementProgressEntry[]
  requiredCurriculumNumbers: Set<string>
  transcriptNumbers: Set<string>
  curriculumGraph?: CurriculumGraph | null
  expanded: boolean
  t: (key: string) => string
  onToggle: (bucket: RequirementProgressEntry, pool: ElectiveBucket) => void
}

export function ElectivePoolRow({
  pool,
  allPools,
  requirementBuckets,
  requiredCurriculumNumbers,
  transcriptNumbers,
  curriculumGraph,
  expanded,
  t,
  onToggle,
}: ElectivePoolRowProps) {
  const linkedBucket = progressBucketForPool(pool, requirementBuckets)
  const bucket: RequirementProgressEntry = linkedBucket ?? {
    requirementGroupId: pool.linkedCreditBucketId ?? pool.groupId,
    title: pool.title,
    status: 'not_started',
    minCredits: pool.minCredits ?? 0,
    creditsCompleted: 0,
    creditsRemaining: pool.minCredits ?? 0,
  }
  const progressDisplay = resolvePoolProgressDisplay(pool, allPools)
  const summary = poolProgressSummary(pool, bucket, t, allPools, {
    curriculumGraph,
    requiredCurriculumNumbers,
  })
  const poolTitle = localizedPoolTitle(pool, t)
  const catalogLines = localizedPoolDescriptions(pool, t)
  const showCatalogExplanation =
    shouldShowPoolCatalogExplanation(pool) &&
    catalogLines.length > 0 &&
    !(expanded && isChainPool(pool) && hasStructuredChainLayout(pool))

  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl border bg-white transition-shadow',
        expanded
          ? 'border-[var(--color-primary)]/35 shadow-sm'
          : 'border-[var(--color-border)]',
      )}
      data-testid={`elective-pool-card-${pool.groupId}`}
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={() => onToggle(bucket, pool)}
        className={cn(
          'flex w-full items-center gap-4 px-4 py-3 text-start transition',
          'hover:bg-[var(--color-surface-muted)]/50',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--color-primary)]/30',
        )}
      >
        <div className="min-w-0 flex-1">
          <p className="font-medium leading-snug">{poolTitle}</p>
          <div className="mt-1.5">
            <PoolRuleBadge pool={pool} t={t} />
          </div>
          {showCatalogExplanation && !expanded ? (
            <div className="mt-2">
              <PoolCatalogExplanation
                lines={catalogLines}
                heading={t('progress.electiveExplorer.catalogRuleHeading')}
                compact
              />
            </div>
          ) : null}
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">
            {interpolateTemplate(t('progress.electiveExplorer.countedSummary'), {
              counted: summary.counted,
              listed: summary.listed,
              credits: formatCredits(summary.creditsCompleted),
            })}
            {pool.courseListSource === 'vault_union'
              ? ` · ${t('progress.electiveExplorer.vaultUnionHint')}`
              : ''}
          </p>
          <PoolProgressStrip
            pool={pool}
            allPools={allPools}
            linkedBucket={linkedBucket}
            summary={summary}
            progressDisplay={progressDisplay}
            t={t}
          />
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <PoolProgressBadge
            pool={pool}
            allPools={allPools}
            progressDisplay={progressDisplay}
            linkedBucket={linkedBucket}
            summary={summary}
          />
          <ChevronDown
            className={cn(
              'h-5 w-5 text-[var(--color-text-muted)] transition-transform duration-200',
              expanded && 'rotate-180',
            )}
            aria-hidden
          />
        </div>
      </button>

      {expanded ? (
        <div className="border-t border-[var(--color-border)] bg-[var(--color-surface-muted)]/20 px-4 py-4">
          {showCatalogExplanation ? (
            <div className="mb-4">
              <PoolCatalogExplanation
                lines={catalogLines}
                heading={t('progress.electiveExplorer.catalogRuleHeading')}
              />
            </div>
          ) : null}
          <ElectivePoolCourseList
            pool={pool}
            allPools={allPools}
            bucket={bucket}
            transcriptNumbers={transcriptNumbers}
            requiredCurriculumNumbers={requiredCurriculumNumbers}
            curriculumGraph={curriculumGraph}
            t={t}
          />
        </div>
      ) : null}
    </div>
  )
}
