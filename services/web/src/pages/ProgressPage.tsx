import { Link, useSearchParams } from 'react-router-dom'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'
import { progressApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import {
  ProgressEmptyTranscriptHint,
  RequirementBucketRow,
} from '../components/progress/ProgressSections'
import { ProgressAttentionPanel } from '../components/progress/ProgressAttentionPanel'
import { ProgressCompletionCelebration } from '../components/progress/ProgressCompletionCelebration'
import { ProgressPageNav } from '../components/progress/ProgressPageNav'
import { CurriculumGraphSection } from '../components/progress/CurriculumGraphSection'
import { ElectivePoolsPanel } from '../components/progress/ElectivePoolsPanel'
import { ElectivePoolsPanelSkeleton } from '../components/progress/ElectivePoolsPanelSkeleton'
import { ProgressLoadingSkeleton } from '../components/progress/ProgressLoadingSkeleton'
import { ProgressSummaryCard } from '../components/progress/ProgressSummaryCard'
import { Card, EmptyState, PageHeader } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { formatCredits } from '../lib/utils'
import {
  buildFullTranscriptCourseNumbers,
  buildRequiredCurriculumCourseNumbers,
  findPoolsForBucket,
} from '../lib/electivePools'
import {
  bucketCompletionPercent,
  countAttentionItems,
  filterRemainingMandatoryCourses,
  hasActionableGaps,
  partitionRequirementBuckets,
} from '../lib/graduationProgress'
import type { ElectiveBucket, RequirementProgressEntry } from '../types/api'

const CURRICULUM_GRAPH_STALE_MS = 5 * 60 * 1000

function scrollToPoolPanel() {
  requestAnimationFrame(() => {
    document.getElementById('elective-pools-panel')?.scrollIntoView?.({
      behavior: 'smooth',
      block: 'start',
    })
  })
}

export function ProgressPage() {
  const { t } = useTranslation()
  const [searchParams, setSearchParams] = useSearchParams()
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
  const progressCourseNumbers = useMemo(
    () =>
      progressQuery.data?.graduationProgress
        ? buildFullTranscriptCourseNumbers(progressQuery.data.graduationProgress)
        : new Set<string>(),
    [progressQuery.data?.graduationProgress],
  )
  const requiredCurriculumNumbers = useMemo(
    () =>
      buildRequiredCurriculumCourseNumbers(requirementProgress, {
        curriculumGraph: curriculumQuery.data?.curriculumGraph,
        remainingMandatory: progressQuery.data?.graduationProgress?.remainingMandatoryCourses,
        completedMandatory: progressQuery.data?.graduationProgress?.completedMandatoryCourses,
      }),
    [
      curriculumQuery.data?.curriculumGraph,
      progressQuery.data?.graduationProgress?.completedMandatoryCourses,
      progressQuery.data?.graduationProgress?.remainingMandatoryCourses,
      requirementProgress,
    ],
  )

  useEffect(() => {
    const poolId = searchParams.get('pool')
    if (!poolId || !electivePools.some((pool) => pool.groupId === poolId)) return
    setExpandedPoolId(poolId)
    scrollToPoolPanel()
  }, [electivePools, searchParams])

  const handleExplorePool = useCallback(
    (_bucket: RequirementProgressEntry, pool: ElectiveBucket) => {
      setExpandedPoolId(pool.groupId)
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous)
          next.set('pool', pool.groupId)
          return next
        },
        { replace: true },
      )
      scrollToPoolPanel()
    },
    [setSearchParams],
  )

  const handleExpandedPoolChange = useCallback(
    (_bucket: RequirementProgressEntry, pool: ElectiveBucket | null) => {
      const nextPoolId = pool?.groupId ?? null
      setExpandedPoolId(nextPoolId)
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous)
          if (nextPoolId) {
            next.set('pool', nextPoolId)
          } else {
            next.delete('pool')
          }
          return next
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  if (progressQuery.isLoading) {
    return <ProgressLoadingSkeleton />
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
  if (!progress) {
    return (
      <EmptyState
        title={t('progress.unavailable')}
        description={t('progress.emptyProgress')}
      />
    )
  }

  const statusKey = `progress.statusSummary.${progress.statusSummary}` as const
  const statusLabel =
    t(statusKey) !== statusKey
      ? t(statusKey)
      : progress.statusSummary.replace(/_/g, ' ')

  const { mandatory } = partitionRequirementBuckets(progress.requirementProgress)
  const showTranscriptHint =
    progress.statusSummary === 'not_started' || progress.completedCredits <= 0
  const curriculumGraph = curriculumQuery.data?.curriculumGraph
  const showAttention = hasActionableGaps(progress, curriculumGraph)
  const attentionCount = countAttentionItems(progress, curriculumGraph)
  const showCurriculum = Boolean(curriculumGraph)
  const showPools =
    !curriculumQuery.isLoading || curriculumQuery.data
      ? electivePools.length > 0
      : false
  const showCelebration =
    !showAttention &&
    (progress.statusSummary === 'complete' ||
      progress.statusSummary === 'mandatory_requirements_met')
  const mandatoryRemainingCount = filterRemainingMandatoryCourses(
    progress.remainingMandatoryCourses,
    progress.completedMandatoryCourses,
    { curriculumGraph, progress },
  ).length
  const mandatoryCreditsCompleted = mandatory.reduce(
    (sum, bucket) => sum + bucket.creditsCompleted,
    0,
  )
  const mandatoryCreditsRequired = mandatory.reduce((sum, bucket) => sum + bucket.minCredits, 0)
  const mandatoryAggregatePercent = bucketCompletionPercent(
    mandatoryCreditsCompleted,
    mandatoryCreditsRequired,
  )
  const navSections = [
    { id: 'progress-overview', label: t('progress.nav.overview') },
    ...(showAttention
      ? [{ id: 'progress-attention', label: t('progress.nav.attention') }]
      : []),
    ...(mandatory.length
      ? [{ id: 'progress-mandatory', label: t('progress.nav.mandatory') }]
      : []),
    ...(showPools ? [{ id: 'elective-pools-panel', label: t('progress.nav.pools') }] : []),
    ...(showCurriculum
      ? [{ id: 'progress-curriculum', label: t('progress.nav.curriculum') }]
      : []),
  ]

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t('progress.title')}
        description={t('progress.pageSubtitle')}
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

      <ProgressSummaryCard
        progress={progress}
        statusLabel={statusLabel}
        attentionCount={attentionCount}
        mandatoryRemainingCount={mandatoryRemainingCount}
        curriculumGraph={curriculumGraph}
        t={t}
      />

      <ProgressPageNav sections={navSections} t={t} />

      {showCelebration ? (
        <ProgressCompletionCelebration progress={progress} statusLabel={statusLabel} t={t} />
      ) : null}

      {showAttention ? (
        <ProgressAttentionPanel
          progress={progress}
          curriculumGraph={curriculumGraph}
          t={t}
        />
      ) : null}

      {mandatory.length ? (
        <Card className="scroll-mt-24" id="progress-mandatory">
          <div className="mb-4 space-y-3">
            <div>
              <h2 className="text-lg font-semibold">{t('progress.mandatoryBuckets')}</h2>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                {t('progress.mandatoryBucketsHint')}
              </p>
            </div>
            <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                <span className="font-medium">{t('progress.mandatoryAggregate')}</span>
                <span className="tabular-nums text-[var(--color-text-muted)]">
                  {formatCredits(mandatoryCreditsCompleted)} / {formatCredits(mandatoryCreditsRequired)}{' '}
                  {t('common.credits')}
                </span>
              </div>
              <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                {t('progress.mandatoryAggregateHint')}
              </p>
              <div
                className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={Math.round(mandatoryAggregatePercent)}
                aria-label={t('progress.mandatoryBuckets')}
              >
                <div
                  className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-500"
                  style={{ width: `${mandatoryAggregatePercent}%` }}
                />
              </div>
            </div>
          </div>
          <div className="space-y-3">
            {mandatory.map((bucket) => (
              <RequirementBucketRow
                key={bucket.requirementGroupId}
                bucket={bucket}
                linkedPools={findPoolsForBucket(bucket, electivePools)}
                onExplorePool={electivePools.length ? handleExplorePool : undefined}
                curriculumGraph={curriculumGraph}
                t={t}
              />
            ))}
          </div>
        </Card>
      ) : null}

      {curriculumQuery.isLoading && !curriculumQuery.data ? (
        <ElectivePoolsPanelSkeleton />
      ) : electivePools.length ? (
        <ElectivePoolsPanel
          pools={electivePools}
          requirementBuckets={requirementProgress}
          requiredCurriculumNumbers={requiredCurriculumNumbers}
          transcriptNumbers={progressCourseNumbers}
          curriculumGraph={curriculumGraph}
          graduationProgress={progress}
          expandedPoolId={expandedPoolId}
          deepLinkPoolId={searchParams.get('pool')}
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

      {curriculumGraph?.advisories?.length ? (
        <Card className="scroll-mt-24 border-sky-200/80 bg-sky-50/50">
          <h2 className="text-sm font-semibold text-sky-950">{t('progress.curriculumAdvisories')}</h2>
          <ul className="mt-2 space-y-2">
            {curriculumGraph.advisories.map((advisory) => (
              <li key={advisory.code} className="text-sm text-sky-900">
                {advisory.message}
              </li>
            ))}
          </ul>
        </Card>
      ) : null}

      {showCurriculum ? (
        <div id="progress-curriculum">
          <CurriculumGraphSection graph={curriculumGraph!} t={t} />
        </div>
      ) : null}

      {progress.assumptionKeys?.length || progress.assumptions?.length ? (
        <details className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4">
          <summary className="cursor-pointer text-sm font-medium">{t('progress.assumptions')}</summary>
          <ul className="mt-3 list-disc space-y-2 ps-5 text-sm text-[var(--color-text-muted)]">
            {(progress.assumptionKeys ?? []).map((key) => {
              const labelKey = `progress.assumptionItems.${key}` as const
              const translated = t(labelKey)
              const fallback =
                progress.assumptions?.[progress.assumptionKeys?.indexOf(key) ?? -1] ?? key
              return <li key={key}>{translated !== labelKey ? translated : fallback}</li>
            })}
            {!progress.assumptionKeys?.length
              ? progress.assumptions?.map((assumption) => (
                  <li key={assumption}>{assumption}</li>
                ))
              : null}
          </ul>
        </details>
      ) : null}
    </div>
  )
}
