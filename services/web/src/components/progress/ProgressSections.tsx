import { Link } from 'react-router-dom'
import { ChevronRight, Layers } from 'lucide-react'
import { AlertTriangle, BookOpen, ClipboardList } from 'lucide-react'
import { Badge, Card } from '../ui/Card'
import { Button } from '../ui/Button'
import { bucketCompletionPercent, statusBadgeTone } from '../../lib/graduationProgress'
import { localizedBucketTitle, localizedPoolTitle } from '../../lib/electivePools'
import { formatCredits } from '../../lib/utils'
import type { CourseProgressEntry, ElectiveBucket, RequirementProgressEntry } from '../../types/api'
import type { useTranslation } from '../../i18n'

type TFn = ReturnType<typeof useTranslation>['t']

export function RequirementBucketRow({
  bucket,
  t,
  linkedPools = [],
  onExplorePool,
}: {
  bucket: RequirementProgressEntry
  t: TFn
  linkedPools?: ElectiveBucket[]
  onExplorePool?: (bucket: RequirementProgressEntry, pool: ElectiveBucket) => void
}) {
  const percent = bucketCompletionPercent(bucket.creditsCompleted, bucket.minCredits)
  const statusKey = `progress.bucketStatus.${bucket.status}` as const
  const translated = t(statusKey)
  const statusLabel =
    translated !== statusKey ? translated : bucket.status.replace(/_/g, ' ')

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-white/70 px-4 py-3">
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium">{localizedBucketTitle(bucket, t)}</p>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
            {bucket.eligibilityEnforcement === 'strict_pool'
              ? t('progress.strictPool')
              : t('progress.creditBucketOnly')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={statusBadgeTone(bucket.status)}>{statusLabel}</Badge>
          <span className="text-sm tabular-nums text-[var(--color-text-muted)]">
            {formatCredits(bucket.creditsCompleted)} / {formatCredits(bucket.minCredits)}
          </span>
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
        <div
          className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
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
                {(pool.courseCount ?? pool.courses.length) > 0 ? (
                  <span className="rounded-full bg-[var(--color-surface-muted)] px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--color-text-muted)]">
                    {pool.courseCount ?? pool.courses.length}
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
    </div>
  )
}

export function CourseChipList({ courses }: { courses: CourseProgressEntry[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {courses.map((course) => (
        <li key={course.courseId}>
          <Link
            to="/catalog"
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

export function ProgressAlertCard({
  tone,
  title,
  description,
  children,
}: {
  tone: 'warning' | 'danger'
  title: string
  description: string
  children?: React.ReactNode
}) {
  const border =
    tone === 'danger' ? 'border-red-200 bg-red-50/60' : 'border-amber-200 bg-amber-50/60'
  const iconColor = tone === 'danger' ? 'text-red-700' : 'text-amber-700'

  return (
    <Card className={border}>
      <div className="flex gap-3">
        <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${iconColor}`} />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold">{title}</h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">{description}</p>
          {children ? <div className="mt-3">{children}</div> : null}
        </div>
      </div>
    </Card>
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
