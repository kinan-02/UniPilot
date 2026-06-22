import { Link } from 'react-router-dom'
import { useCallback, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'
import { progressApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import {
  CourseChipList,
  ProgressAlertCard,
  ProgressEmptyTranscriptHint,
  RequirementBucketRow,
} from '../components/progress/ProgressSections'
import { CurriculumGraphSection } from '../components/progress/CurriculumGraphSection'
import { ElectivePoolsPanel } from '../components/progress/ElectivePoolsPanel'
import { ElectivePoolsPanelSkeleton } from '../components/progress/ElectivePoolsPanelSkeleton'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import {
  buildRequiredCurriculumCourseNumbers,
  buildTranscriptCourseNumbers,
  findPoolsForBucket,
  localizedBucketTitle,
} from '../lib/electivePools'
import {
  partitionRequirementBuckets,
  progressCatalogSubtitle,
  statusBadgeTone,
} from '../lib/graduationProgress'
import { formatCredits, formatPercent } from '../lib/utils'
import type { ElectiveBucket, RequirementProgressEntry } from '../types/api'

const CURRICULUM_GRAPH_STALE_MS = 5 * 60 * 1000

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--color-text-muted)]">{hint}</p> : null}
    </Card>
  )
}

export function ProgressPage() {
  const { t } = useTranslation()
  const [expandedPoolId, setExpandedPoolId] = useState<string | null>(null)
  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: progressApi.get,
    retry: false,
  })
  const curriculumQuery = useQuery({
    queryKey: ['curriculum-graph'],
    queryFn: progressApi.curriculumGraph,
    retry: false,
    staleTime: CURRICULUM_GRAPH_STALE_MS,
  })
  const electivePools = curriculumQuery.data?.curriculumGraph?.electiveBuckets ?? []
  const requirementProgress = progressQuery.data?.graduationProgress?.requirementProgress ?? []
  const transcriptNumbers = useMemo(
    () => buildTranscriptCourseNumbers(requirementProgress),
    [requirementProgress],
  )
  const requiredCurriculumNumbers = useMemo(
    () =>
      buildRequiredCurriculumCourseNumbers(requirementProgress, {
        curriculumGraph: curriculumQuery.data?.curriculumGraph,
        remainingMandatory: progressQuery.data?.graduationProgress?.remainingMandatoryCourses,
      }),
    [
      curriculumQuery.data?.curriculumGraph,
      progressQuery.data?.graduationProgress?.remainingMandatoryCourses,
      requirementProgress,
    ],
  )
  const poolsByBucketId = useMemo(() => {
    if (!requirementProgress.length) return new Map<string, ElectiveBucket[]>()
    const entries = new Map<string, ElectiveBucket[]>()
    for (const bucket of requirementProgress) {
      const pools = findPoolsForBucket(bucket, electivePools)
      if (pools.length) entries.set(bucket.requirementGroupId, pools)
    }
    return entries
  }, [requirementProgress, electivePools])

  const handleExplorePool = useCallback(
    (_selectedBucket: RequirementProgressEntry, pool: ElectiveBucket) => {
      setExpandedPoolId(pool.groupId)
      requestAnimationFrame(() => {
        const panel = document.getElementById('elective-pools-panel')
        panel?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
      })
    },
    [],
  )

  const handleExpandedPoolChange = useCallback(
    (_bucket: RequirementProgressEntry, pool: ElectiveBucket | null) => {
      setExpandedPoolId(pool?.groupId ?? null)
    },
    [],
  )

  if (progressQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  if (progressQuery.isError) {
    const isNoDegree =
      isAuthError(progressQuery.error) && progressQuery.error.status === 400
    const isNoProfile =
      isAuthError(progressQuery.error) && progressQuery.error.status === 404
    const message = isNoDegree
      ? t('progress.noDegree')
      : isNoProfile
        ? t('dashboard.completeProfileHint')
        : t('progress.loadFailed')

    return (
      <EmptyState
        title={t('progress.unavailable')}
        description={message}
        action={
          isNoProfile || isNoDegree ? (
            <Link
              to={isNoProfile ? '/onboarding' : '/profile'}
              className="text-sm font-medium text-[var(--color-primary)]"
            >
              {t('progress.setupProfile')}
            </Link>
          ) : null
        }
      />
    )
  }

  const progress = progressQuery.data?.graduationProgress
  if (!progress) return null

  const statusKey = `progress.statusSummary.${progress.statusSummary}` as const
  const statusLabel =
    t(statusKey) !== statusKey
      ? t(statusKey)
      : progress.statusSummary.replace(/_/g, ' ')

  const { mandatory, elective, generalTechnion } = partitionRequirementBuckets(progress.requirementProgress)
  const subtitle =
    progressCatalogSubtitle(progress) || t('progress.subtitleFallback')
  const showTranscriptHint =
    progress.statusSummary === 'not_started' || progress.completedCredits <= 0

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t('progress.title')}
        description={subtitle}
        action={
          <Link
            to="/transcript"
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
          >
            <BookOpen className="h-4 w-4" />
            {t('progress.updateTranscript')}
          </Link>
        }
      />

      {showTranscriptHint ? <ProgressEmptyTranscriptHint t={t} /> : null}

      {curriculumQuery.data?.curriculumGraph ? (
        <CurriculumGraphSection graph={curriculumQuery.data.curriculumGraph} t={t} />
      ) : null}

      {curriculumQuery.isLoading && !curriculumQuery.data ? (
        <ElectivePoolsPanelSkeleton />
      ) : electivePools.length ? (
        <ElectivePoolsPanel
          pools={electivePools}
          requirementBuckets={requirementProgress}
          requiredCurriculumNumbers={requiredCurriculumNumbers}
          transcriptNumbers={transcriptNumbers}
          expandedPoolId={expandedPoolId}
          t={t}
          onExpandedPoolChange={handleExpandedPoolChange}
        />
      ) : curriculumQuery.isError ? (
        <Card className="border-dashed">
          <p className="text-sm text-[var(--color-text-muted)]">
            {t('progress.electiveExplorer.loadFailed')}
          </p>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile
          label={t('progress.overallCompletion')}
          value={formatPercent(progress.completionPercentage)}
          hint={`${formatCredits(progress.completedCredits)} / ${formatCredits(progress.totalRequiredCredits)}`}
        />
        <StatTile
          label={t('progress.creditsRemaining')}
          value={formatCredits(progress.creditsRemaining)}
        />
        <StatTile
          label={t('progress.electiveProgress')}
          value={formatCredits(progress.completedElectiveCredits ?? 0)}
          hint={
            progress.remainingElectiveCredits
              ? `${t('progress.electiveRemaining')}: ${formatCredits(progress.remainingElectiveCredits)}`
              : undefined
          }
        />
        <StatTile
          label={t('progress.status')}
          value={statusLabel}
          hint={
            progress.remainingMandatoryCourses?.length
              ? `${t('progress.mandatoryRemaining')}: ${progress.remainingMandatoryCourses.length}`
              : undefined
          }
        />
      </div>

      <Card>
        <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm text-[var(--color-text-muted)]">{t('progress.overallCompletion')}</p>
            <p className="text-4xl font-semibold tracking-tight">
              {formatPercent(progress.completionPercentage)}
            </p>
          </div>
          <Badge tone={statusBadgeTone(progress.statusSummary)}>{statusLabel}</Badge>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-stone-100">
          <div
            className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-500"
            style={{ width: `${Math.min(progress.completionPercentage, 100)}%` }}
          />
        </div>
        <p className="mt-3 text-sm text-[var(--color-text-muted)]">
          {formatCredits(progress.completedCredits)} {t('progress.creditsCompleted').toLowerCase()} ·{' '}
          {formatCredits(progress.creditsRemaining)} {t('progress.creditsRemaining').toLowerCase()} ·{' '}
          {formatCredits(progress.totalRequiredCredits)} {t('progress.totalRequired').toLowerCase()}
        </p>
      </Card>

      {progress.ineligibleCredits?.length ? (
        <ProgressAlertCard
          tone="warning"
          title={t('progress.ineligibleCredits')}
          description={t('progress.ineligibleCreditsHint')}
        >
          <ul className="space-y-2 text-sm">
            {progress.ineligibleCredits.map((entry) => (
              <li key={`${entry.courseId}-${entry.bucketSuffix ?? entry.reason}`}>
                <span className="font-mono text-[var(--color-primary)]">
                  {entry.courseNumber ?? entry.courseId.slice(-8)}
                </span>
                {' · '}
                {formatCredits(entry.creditsEarned)} {t('common.credits')}
              </li>
            ))}
          </ul>
        </ProgressAlertCard>
      ) : null}

      {progress.missingRequirements?.length ? (
        <ProgressAlertCard
          tone="warning"
          title={t('progress.missingRequirements')}
          description={t('progress.missingRequirementsHint')}
        >
          <ul className="mt-1 space-y-2">
            {progress.missingRequirements.map((item) => (
              <li
                key={item.requirementGroupId}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-white/80 px-3 py-2 text-sm"
              >
                <span>
                  {localizedBucketTitle(
                    { requirementGroupId: item.requirementGroupId, title: item.title },
                    t,
                  )}
                </span>
                <span className="text-[var(--color-text-muted)]">
                  {formatCredits(item.creditsCompleted)} / {formatCredits(item.creditsRequired)}
                </span>
              </li>
            ))}
          </ul>
        </ProgressAlertCard>
      ) : null}

      {progress.remainingMandatoryCourses?.length ? (
        <Card>
          <h2 className="text-sm font-semibold">{t('progress.remainingMandatory')}</h2>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {t('progress.remainingMandatoryHint')}
          </p>
          <div className="mt-4">
            <CourseChipList courses={progress.remainingMandatoryCourses} />
          </div>
        </Card>
      ) : null}

      {mandatory.length || elective.length || generalTechnion.length || electivePools.length ? (
        <div className="space-y-6">
          {generalTechnion.length ? (
            <Card>
              <h2 className="mb-1 text-sm font-semibold">{t('progress.generalTechnionBuckets')}</h2>
              <p className="mb-4 text-sm text-[var(--color-text-muted)]">
                {t('progress.generalTechnionBucketsHint')}
              </p>
              <div className="space-y-3">
                {generalTechnion.map((bucket) => (
                  <RequirementBucketRow
                    key={bucket.requirementGroupId}
                    bucket={bucket}
                    t={t}
                    linkedPools={poolsByBucketId.get(bucket.requirementGroupId) ?? []}
                    onExplorePool={handleExplorePool}
                  />
                ))}
              </div>
            </Card>
          ) : null}
          {mandatory.length || elective.length ? (
            <div className="grid gap-6 xl:grid-cols-2">
              {mandatory.length ? (
                <Card>
                  <h2 className="mb-4 text-sm font-semibold">{t('progress.mandatoryBuckets')}</h2>
                  <div className="space-y-3">
                    {mandatory.map((bucket) => (
                      <RequirementBucketRow
                        key={bucket.requirementGroupId}
                        bucket={bucket}
                        t={t}
                        linkedPools={poolsByBucketId.get(bucket.requirementGroupId) ?? []}
                        onExplorePool={handleExplorePool}
                      />
                    ))}
                  </div>
                </Card>
              ) : null}
              {elective.length ? (
                <Card>
                  <h2 className="mb-4 text-sm font-semibold">{t('progress.electiveBuckets')}</h2>
                  <div className="space-y-3">
                    {elective.map((bucket) => (
                      <RequirementBucketRow
                        key={bucket.requirementGroupId}
                        bucket={bucket}
                        t={t}
                        linkedPools={poolsByBucketId.get(bucket.requirementGroupId) ?? []}
                        onExplorePool={handleExplorePool}
                      />
                    ))}
                  </div>
                </Card>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : (
        <Card>
          <p className="text-sm text-[var(--color-text-muted)]">{t('progress.noBuckets')}</p>
        </Card>
      )}

      {progress.assumptions?.length ? (
        <details className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4">
          <summary className="cursor-pointer text-sm font-medium">{t('progress.assumptions')}</summary>
          <ul className="mt-3 list-disc space-y-2 ps-5 text-sm text-[var(--color-text-muted)]">
            {progress.assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}