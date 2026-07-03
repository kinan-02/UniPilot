import { Badge } from '../ui/Card'
import {
  chainStepPercent,
  interpolateTemplate,
  localizedBucketTitle,
  resolvePoolCreditProgress,
  type PoolProgressDisplay,
  type PoolProgressSummary,
} from '../../lib/electivePools'
import { bucketCompletionPercent } from '../../lib/graduationProgress'
import { formatCredits } from '../../lib/utils'
import type { ElectiveBucket, RequirementProgressEntry } from '../../types/api'

type PoolProgressStripProps = {
  pool: ElectiveBucket
  allPools: ElectiveBucket[]
  linkedBucket: RequirementProgressEntry | undefined
  summary: PoolProgressSummary
  progressDisplay: PoolProgressDisplay
  t: (key: string) => string
}

export function PoolProgressStrip({
  pool,
  allPools,
  linkedBucket,
  summary,
  progressDisplay,
  t,
}: PoolProgressStripProps) {
  if (progressDisplay === 'none' || !linkedBucket) return null

  if (progressDisplay === 'chain_steps') {
    const required = summary.chainStepsRequired ?? pool.rule.chooseCount ?? 1
    const percent = chainStepPercent(summary.chainStepsCompleted, required)
    const creditProgress = resolvePoolCreditProgress(
      pool,
      linkedBucket,
      progressDisplay,
      allPools,
    )
    return (
      <div className="mt-2">
        <div className="mb-1 flex justify-between text-xs text-[var(--color-text-muted)]">
          <span>{t('progress.electiveExplorer.chainProgressLabel')}</span>
          <span className="shrink-0 tabular-nums">
            {interpolateTemplate(t('progress.electiveExplorer.chainProgress'), {
              completed: summary.chainStepsCompleted,
              required,
            })}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full rounded-full bg-violet-500"
            style={{ width: `${percent}%` }}
          />
        </div>
        {creditProgress.displayCreditsCompleted > 0 ? (
          <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
            {interpolateTemplate(t('progress.electiveExplorer.poolCreditsCounted'), {
              credits: formatCredits(creditProgress.displayCreditsCompleted),
              bucketCredits: formatCredits(creditProgress.bucketCreditsCompleted),
              bucketRequired: formatCredits(creditProgress.bucketMinCredits),
            })}
          </p>
        ) : (
          <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
            {t('progress.electiveExplorer.chainIncludedInElectives')}
          </p>
        )}
      </div>
    )
  }

  const creditProgress = resolvePoolCreditProgress(
    pool,
    linkedBucket,
    progressDisplay,
    allPools,
  )
  const barCredits = creditProgress.bucketCreditsCompleted
  const percent = bucketCompletionPercent(barCredits, creditProgress.bucketMinCredits)
  const bucketTitle = localizedBucketTitle(linkedBucket, t)
  const isShared = progressDisplay === 'shared_bucket_credits'

  return (
    <div className="mt-2">
      <div className="mb-1 flex justify-between gap-2 text-xs text-[var(--color-text-muted)]">
        <span className="truncate">{bucketTitle}</span>
        <span className="shrink-0 text-end tabular-nums">
          {isShared
            ? interpolateTemplate(t('progress.electiveExplorer.sharedPoolCreditsLine'), {
                poolCredits: formatCredits(creditProgress.displayCreditsCompleted),
                bucketCredits: formatCredits(creditProgress.bucketCreditsCompleted),
                bucketRequired: formatCredits(creditProgress.bucketMinCredits),
              })
            : `${formatCredits(creditProgress.displayCreditsCompleted)} / ${formatCredits(creditProgress.bucketMinCredits)}`}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
        <div
          className="h-full rounded-full bg-[var(--color-primary)]"
          style={{ width: `${percent}%` }}
        />
      </div>
      {isShared ? (
        <p className="mt-1 text-[11px] text-[var(--color-text-muted)]">
          {t('progress.electiveExplorer.sharedElectiveBucketHint')}
        </p>
      ) : null}
    </div>
  )
}

export function PoolProgressBadge({
  pool,
  allPools,
  progressDisplay,
  linkedBucket,
  summary,
}: {
  pool: ElectiveBucket
  allPools: ElectiveBucket[]
  progressDisplay: PoolProgressDisplay
  linkedBucket: RequirementProgressEntry | undefined
  summary: PoolProgressSummary
}) {
  if (progressDisplay === 'none' || !linkedBucket) return null

  if (progressDisplay === 'chain_steps') {
    const required = summary.chainStepsRequired ?? 1
    const percent = chainStepPercent(summary.chainStepsCompleted, required)
    return (
      <Badge tone={percent >= 100 ? 'success' : 'primary'}>{Math.round(percent)}%</Badge>
    )
  }

  const creditProgress = resolvePoolCreditProgress(
    pool,
    linkedBucket,
    progressDisplay,
    allPools,
  )
  const percent = bucketCompletionPercent(
    creditProgress.bucketCreditsCompleted,
    creditProgress.bucketMinCredits,
  )
  return (
    <Badge tone={linkedBucket.status === 'satisfied' ? 'success' : 'primary'}>
      {`${Math.round(percent)}%`}
    </Badge>
  )
}
