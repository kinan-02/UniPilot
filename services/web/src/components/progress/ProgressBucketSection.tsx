import { useMemo, useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { Card } from '../ui/Card'
import { RequirementBucketRow } from './ProgressSections'
import { bucketCompletionPercent, statusBadgeTone } from '../../lib/graduationProgress'
import { findPoolsForBucket } from '../../lib/electivePools'
import { formatCredits, cn } from '../../lib/utils'
import type { CurriculumGraph, ElectiveBucket, RequirementProgressEntry } from '../../types/api'
import type { useTranslation } from '../../i18n'

type TFn = ReturnType<typeof useTranslation>['t']

function bucketNeedsAttention(bucket: RequirementProgressEntry): boolean {
  if (bucket.status !== 'satisfied') return true
  return bucket.poolConstraints?.constraintsSatisfied === false
}

type ProgressBucketSectionProps = {
  id: string
  title: string
  hint: string
  buckets: RequirementProgressEntry[]
  electivePools?: ElectiveBucket[]
  curriculumGraph?: CurriculumGraph | null
  onExplorePool?: (bucket: RequirementProgressEntry, pool: ElectiveBucket) => void
  aggregateLabel?: string
  aggregateHint?: string
  t: TFn
}

export function ProgressBucketSection({
  id,
  title,
  hint,
  buckets,
  electivePools = [],
  curriculumGraph,
  onExplorePool,
  aggregateLabel,
  aggregateHint,
  t,
}: ProgressBucketSectionProps) {
  const [showCompleted, setShowCompleted] = useState(false)

  const { activeBuckets, completedBuckets, creditsCompleted, creditsRequired } = useMemo(() => {
    const active: RequirementProgressEntry[] = []
    const completed: RequirementProgressEntry[] = []
    let completedCredits = 0
    let requiredCredits = 0

    for (const bucket of buckets) {
      completedCredits += bucket.creditsCompleted
      requiredCredits += bucket.minCredits
      if (bucketNeedsAttention(bucket)) {
        active.push(bucket)
      } else {
        completed.push(bucket)
      }
    }

    return {
      activeBuckets: active,
      completedBuckets: completed,
      creditsCompleted: completedCredits,
      creditsRequired: requiredCredits,
    }
  }, [buckets])

  const aggregatePercent = bucketCompletionPercent(creditsCompleted, creditsRequired)
  const tone = statusBadgeTone(
    activeBuckets.length === 0 ? 'satisfied' : activeBuckets.some((b) => b.status === 'not_started') ? 'not_started' : 'in_progress',
  )
  const progressBarClass =
    tone === 'success'
      ? 'bg-emerald-500'
      : tone === 'primary'
        ? 'bg-[var(--color-primary)]'
        : 'bg-amber-500'

  if (!buckets.length) return null

  return (
    <Card className="scroll-mt-24" id={id}>
      <div className="mb-5 space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold">{title}</h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)] text-pretty">{hint}</p>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-4 py-2.5 text-end">
            <p className="text-xs font-medium text-[var(--color-text-muted)]">
              {aggregateLabel ?? t('progress.bucketSection.aggregate')}
            </p>
            <p className="mt-0.5 text-sm font-semibold tabular-nums">
              {formatCredits(creditsCompleted)} / {formatCredits(creditsRequired)}{' '}
              <span className="font-normal text-[var(--color-text-muted)]">{t('common.credits')}</span>
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-[var(--color-border)] bg-white/80 px-4 py-3">
          {aggregateHint ? (
            <p className="mb-2 text-xs text-[var(--color-text-muted)] text-pretty">{aggregateHint}</p>
          ) : null}
          <div
            className="h-2 overflow-hidden rounded-full bg-stone-100"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(aggregatePercent)}
            aria-label={title}
          >
            <div
              className={cn('h-full rounded-full transition-all duration-500', progressBarClass)}
              style={{ width: `${aggregatePercent}%` }}
            />
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-[var(--color-text-muted)]">
            <span>
              {interpolateBucketSummary(t('progress.bucketSection.inProgress'), activeBuckets.length)}
            </span>
            <span>
              {interpolateBucketSummary(t('progress.bucketSection.complete'), completedBuckets.length)}
            </span>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {activeBuckets.map((bucket) => (
          <RequirementBucketRow
            key={bucket.requirementGroupId}
            bucket={bucket}
            linkedPools={findPoolsForBucket(bucket, electivePools)}
            onExplorePool={onExplorePool}
            curriculumGraph={curriculumGraph}
            defaultExpanded
            t={t}
          />
        ))}

        {completedBuckets.length ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)]">
            <button
              type="button"
              onClick={() => setShowCompleted((value) => !value)}
              aria-expanded={showCompleted}
              className="flex w-full items-center justify-between gap-3 px-4 py-3 text-start text-sm font-medium transition hover:bg-[var(--color-surface-muted)]/50"
            >
              <span>
                {interpolateBucketSummary(
                  t('progress.bucketSection.showCompleted'),
                  completedBuckets.length,
                )}
              </span>
              <ChevronDown
                className={cn(
                  'h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition-transform',
                  showCompleted && 'rotate-180',
                )}
                aria-hidden
              />
            </button>
            {showCompleted ? (
              <div className="space-y-3 border-t border-[var(--color-border)] px-3 py-3">
                {completedBuckets.map((bucket) => (
                  <RequirementBucketRow
                    key={bucket.requirementGroupId}
                    bucket={bucket}
                    linkedPools={findPoolsForBucket(bucket, electivePools)}
                    onExplorePool={onExplorePool}
                    curriculumGraph={curriculumGraph}
                    t={t}
                  />
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </Card>
  )
}

function interpolateBucketSummary(template: string, count: number): string {
  return template.replace('{count}', String(count))
}
