import { Link } from 'react-router-dom'
import { BookOpen, ChevronRight, ClipboardList, Layers } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { bucketCompletionPercent, statusBadgeTone } from '../../lib/graduationProgress'
import { catalogSearchLink, dedupedPoolListedCount, interpolateTemplate, localizedBucketTitle, localizedPoolTitle } from '../../lib/electivePools'
import { formatCredits } from '../../lib/utils'
import type { CourseProgressEntry, CurriculumGraph, ElectiveBucket, PoolConstraintsSummary, RequirementProgressEntry } from '../../types/api'
import type { useTranslation } from '../../i18n'

type TFn = ReturnType<typeof useTranslation>['t']

function PoolConstraintSummary({
  constraints,
  t,
}: {
  constraints: PoolConstraintsSummary
  t: TFn
}) {
  if (constraints.constraintsSatisfied !== false) return null

  const unsatisfied = (constraints.allPools ?? []).filter((entry) => entry.satisfied === false)
  if (!unsatisfied.length) return null

  return (
    <div
      className="mt-3 rounded-lg border border-amber-200/80 bg-amber-50/60 px-3 py-2.5"
      data-testid="pool-constraint-summary"
    >
      <p className="text-xs font-medium text-amber-950">{t('progress.poolConstraints.title')}</p>
      <ul className="mt-2 space-y-1.5">
        {unsatisfied.map((entry) => {
          const progressLabel =
            entry.stepsRequired != null
              ? interpolateTemplate(t('progress.poolConstraints.steps'), {
                  completed: entry.stepsCompleted ?? 0,
                  required: entry.stepsRequired,
                })
              : entry.creditsRequired != null
                ? interpolateTemplate(t('progress.poolConstraints.credits'), {
                    completed: entry.creditsCompleted ?? 0,
                    required: entry.creditsRequired,
                  })
                : null
          return (
            <li
              key={entry.requirementGroupId ?? entry.title}
              className="text-xs text-amber-900 text-pretty"
            >
              <span className="font-medium">{entry.title ?? entry.requirementGroupId}</span>
              {progressLabel ? <span className="text-amber-800/90"> — {progressLabel}</span> : null}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function RequirementBucketRow({
  bucket,
  t,
  linkedPools = [],
  onExplorePool,
  curriculumGraph,
  defaultExpanded = false,
  compact = false,
}: {
  bucket: RequirementProgressEntry
  t: TFn
  linkedPools?: ElectiveBucket[]
  onExplorePool?: (bucket: RequirementProgressEntry, pool: ElectiveBucket) => void
  curriculumGraph?: CurriculumGraph | null
  defaultExpanded?: boolean
  compact?: boolean
}) {
  const percent = bucketCompletionPercent(bucket.creditsCompleted, bucket.minCredits)
  const statusKey = `progress.bucketStatus.${bucket.status}` as const
  const translated = t(statusKey)
  const statusLabel =
    translated !== statusKey ? translated : bucket.status.replace(/_/g, ' ')
  const hasConstraintGap = bucket.poolConstraints?.constraintsSatisfied === false
  const showDetails = defaultExpanded || bucket.status !== 'satisfied' || hasConstraintGap

  const header = (
    <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-sm font-medium">{localizedBucketTitle(bucket, t)}</p>
        {!compact ? (
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
            {bucket.eligibilityEnforcement === 'strict_pool'
              ? t('progress.strictPool')
              : t('progress.creditBucketOnly')}
          </p>
        ) : null}
      </div>
      <div className="flex items-center gap-2">
        <Badge tone={statusBadgeTone(bucket.status)}>{statusLabel}</Badge>
        <span className="text-sm tabular-nums text-[var(--color-text-muted)]">
          {formatCredits(bucket.creditsCompleted)} / {formatCredits(bucket.minCredits)}
        </span>
      </div>
    </div>
  )

  const progressBar = (
    <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
      <div
        className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-500"
        style={{ width: `${percent}%` }}
      />
    </div>
  )

  const body = (
    <>
      {bucket.poolConstraints ? (
        <PoolConstraintSummary constraints={bucket.poolConstraints} t={t} />
      ) : null}
      {linkedPools.length && onExplorePool ? (
        <div className="mt-3 rounded-lg border border-dashed border-[var(--color-primary)]/20 bg-[var(--color-surface-muted)]/50 px-3 py-2.5">
          <p className="mb-2 text-xs font-medium text-[var(--color-text-muted)]">
            {linkedPools.length === 1
              ? t('progress.electiveExplorer.linkedPoolSingular')
              : t('progress.electiveExplorer.linkedPoolPlural')}
          </p>
          <div className="flex flex-wrap gap-2">
            {linkedPools.map((pool) => (
              <Button
                key={pool.groupId}
                type="button"
                variant="secondary"
                size="sm"
                data-testid={`explore-pool-${bucket.requirementGroupId}-${pool.groupId}`}
                onClick={() => onExplorePool(bucket, pool)}
                className="max-w-full border-[var(--color-primary)]/15 bg-white hover:border-[var(--color-primary)]/35"
              >
                <Layers className="h-3.5 w-3.5 shrink-0 text-[var(--color-primary)]" />
                <span className="truncate">
                  {linkedPools.length > 1
                    ? localizedPoolTitle(pool, t)
                    : t('progress.electiveExplorer.open')}
                </span>
                {(dedupedPoolListedCount(pool, {
                  countedNumbers: new Set<string>(),
                  curriculumGraph,
                })) > 0 ? (
                  <span className="rounded-full bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--color-text-muted)]">
                    {dedupedPoolListedCount(pool, {
                      countedNumbers: new Set<string>(),
                      curriculumGraph,
                    })}
                  </span>
                ) : null}
                <ChevronRight className="h-3.5 w-3.5 shrink-0 opacity-60" />
              </Button>
            ))}
          </div>
        </div>
      ) : null}
      {bucket.completedCourses?.length ? (
        <div className="mt-3">
          <p className="mb-1.5 text-xs font-medium text-[var(--color-text-muted)]">
            {t('progress.completedInBucket')}
          </p>
          <CourseChipList courses={bucket.completedCourses} />
        </div>
      ) : null}
      {bucket.remainingCourses?.length ? (
        <div className="mt-3">
          <p className="mb-1.5 text-xs font-medium text-amber-800/80">
            {t('progress.remainingInBucket')}
          </p>
          <CourseChipList courses={bucket.remainingCourses} />
        </div>
      ) : null}
    </>
  )

  if (!showDetails) {
    return (
      <details className="group rounded-xl border border-[var(--color-border)] bg-white/70 px-4 py-3">
        <summary className="cursor-pointer list-none [&::-webkit-details-marker]:hidden">
          {header}
          <div className="mt-2">{progressBar}</div>
        </summary>
        <div className="mt-3 border-t border-[var(--color-border)] pt-3">{body}</div>
      </details>
    )
  }

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white/70 px-4 py-3">
      {header}
      {progressBar}
      {body}
    </div>
  )
}

export function CourseChipList({ courses }: { courses: CourseProgressEntry[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {courses.map((course) => (
        <li key={course.courseId}>
          <Link
            to={course.courseNumber ? catalogSearchLink(course.courseNumber) : '/catalog'}
            className="inline-flex max-w-full flex-col rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-2.5 py-1.5 text-start transition hover:border-[var(--color-primary)]/30"
          >
            <span className="font-mono text-xs font-medium text-[var(--color-primary)]">
              {course.courseNumber ?? course.courseId.slice(-8)}
            </span>
            {course.courseTitle ? (
              <span className="truncate text-xs text-[var(--color-text-muted)]">
                {course.courseTitle}
              </span>
            ) : null}
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function ProgressEmptyTranscriptHint({ t }: { t: TFn }) {
  return (
    <Card className="border-dashed">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex gap-3">
          <ClipboardList className="h-8 w-8 text-[var(--color-primary)]" />
          <div>
            <p className="text-sm font-medium">{t('progress.noTranscriptHint')}</p>
          </div>
        </div>
        <Link
          to="/transcript"
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white"
        >
          <BookOpen className="h-4 w-4" />
          {t('progress.updateTranscript')}
        </Link>
      </div>
    </Card>
  )
}
