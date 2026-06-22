import { ChevronRight, GitBranch, Layers, ListChecks } from 'lucide-react'
import { Badge } from '../ui/Card'
import { Button } from '../ui/Button'
import {
  categoryAccentClass,
  categorySurfaceClass,
  classifyPool,
  interpolateTemplate,
  poolCategoryTranslationKey,
  poolProgressSummary,
  progressBucketForPool,
} from '../../lib/electivePools'
import { bucketCompletionPercent } from '../../lib/graduationProgress'
import { cn, formatCredits } from '../../lib/utils'
import { PoolRuleBadge } from './PoolRuleBadge'
import type { ElectiveBucket, RequirementProgressEntry } from '../../types/api'

type ElectivePoolCardProps = {
  pool: ElectiveBucket
  requirementBuckets: RequirementProgressEntry[]
  t: (key: string) => string
  onExplore: (bucket: RequirementProgressEntry, pool: ElectiveBucket) => void
}

function categoryIcon(category: ReturnType<typeof classifyPool>) {
  switch (category) {
    case 'focus_chain':
    case 'choose_n':
      return GitBranch
    case 'credit_pool':
      return Layers
    default:
      return ListChecks
  }
}

export function ElectivePoolCard({
  pool,
  requirementBuckets,
  t,
  onExplore,
}: ElectivePoolCardProps) {
  const category = classifyPool(pool)
  const Icon = categoryIcon(category)
  const linkedBucket = progressBucketForPool(pool, requirementBuckets)
  const bucket: RequirementProgressEntry = linkedBucket ?? {
    requirementGroupId: pool.linkedCreditBucketId ?? pool.groupId,
    title: pool.title,
    status: 'not_started',
    minCredits: pool.minCredits ?? 0,
    creditsCompleted: 0,
    creditsRemaining: pool.minCredits ?? 0,
  }
  const summary = poolProgressSummary(pool, bucket)
  const categoryKey = poolCategoryTranslationKey(category)
  const categoryLabel = t(categoryKey) !== categoryKey ? t(categoryKey) : category
  const completionPercent = linkedBucket
    ? bucketCompletionPercent(linkedBucket.creditsCompleted, linkedBucket.minCredits)
    : 0
  const isSatisfied = linkedBucket?.status === 'satisfied'

  const openExplorer = () => onExplore(bucket, pool)

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={openExplorer}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          openExplorer()
        }
      }}
      className={cn(
        'group flex h-full cursor-pointer flex-col rounded-xl border border-[var(--color-border)] border-s-4 bg-white/90 p-4 text-start shadow-sm transition',
        categoryAccentClass(category),
        'hover:-translate-y-0.5 hover:border-[var(--color-primary)]/30 hover:shadow-[var(--shadow-soft)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40',
        isSatisfied && 'ring-1 ring-emerald-200',
      )}
      data-testid={`elective-pool-card-${pool.groupId}`}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={cn(
              'inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl',
              categorySurfaceClass(category),
            )}
          >
            <Icon className="h-4 w-4" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-semibold leading-snug">{pool.title ?? pool.groupId}</p>
            <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{categoryLabel}</p>
          </div>
        </div>
        {linkedBucket ? (
          <Badge tone={isSatisfied ? 'success' : 'primary'}>
            {formatCredits(linkedBucket.creditsCompleted)} / {formatCredits(linkedBucket.minCredits)}
          </Badge>
        ) : null}
      </div>

      <PoolRuleBadge pool={pool} t={t} />

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-full bg-[var(--color-surface-muted)] px-2.5 py-1 text-xs font-medium text-[var(--color-text-muted)]">
          {interpolateTemplate(t('progress.electiveExplorer.coursesListed'), {
            count: pool.courseCount ?? pool.courses.length,
          })}
        </span>
        {summary.counted > 0 ? (
          <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
            {interpolateTemplate(t('progress.electiveExplorer.countedChip'), {
              count: summary.counted,
            })}
          </span>
        ) : null}
      </div>

      {linkedBucket ? (
        <div className="mt-3">
          <div className="mb-1 flex justify-between text-xs text-[var(--color-text-muted)]">
            <span className="truncate pe-2">
              {linkedBucket.title ?? t('progress.electiveExplorer.linkedBucket')}
            </span>
            <span className="shrink-0 tabular-nums">{Math.round(completionPercent)}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-stone-100">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                isSatisfied ? 'bg-emerald-500' : 'bg-[var(--color-accent)]',
              )}
              style={{ width: `${completionPercent}%` }}
            />
          </div>
        </div>
      ) : null}

      <p className="mt-3 line-clamp-2 text-xs text-[var(--color-text-muted)]">
        {summary.chainStepsRequired != null
          ? interpolateTemplate(t('progress.electiveExplorer.chainProgress'), {
              completed: summary.chainStepsCompleted,
              required: summary.chainStepsRequired,
            })
          : interpolateTemplate(t('progress.electiveExplorer.countedSummary'), {
              counted: summary.counted,
              listed: summary.listed,
            })}
      </p>

      <div className="mt-auto flex justify-end pt-4">
        <Button
          variant="secondary"
          size="sm"
          data-testid={`explore-pool-catalog-${pool.groupId}`}
          onClick={(event) => {
            event.stopPropagation()
            openExplorer()
          }}
          className="group-hover:border-[var(--color-primary)]/40 group-hover:bg-[var(--color-surface-muted)]"
        >
          {t('progress.electiveExplorer.open')}
          <ChevronRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
        </Button>
      </div>
    </article>
  )
}
