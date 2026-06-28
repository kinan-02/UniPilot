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
import { ProgressSummaryCard } from '../components/progress/ProgressSummaryCard'
import { Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import {
  buildRequiredCurriculumCourseNumbers,
  buildTranscriptCourseNumbers,
  findPoolsForBucket,
} from '../lib/electivePools'
import {
  countAttentionItems,
  hasActionableGaps,
  partitionRequirementBuckets,
  progressCatalogSubtitle,
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
    () => buildTranscriptCourseNumbers(requirementProgress),
    [requirementProgress],
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

  const { mandatory } = partitionRequirementBuckets(progress.requirementProgress)
  const subtitle =
    progressCatalogSubtitle(progress) || t('progress.subtitleFallback')
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
  const navSections = [
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

      <ProgressSummaryCard
        progress={progress}
        statusLabel={statusLabel}
        attentionCount={attentionCount}
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
        <Card id="progress-mandatory">
          <div className="mb-4">
            <h2 className="text-lg font-semibold">{t('progress.mandatoryBuckets')}</h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              {t('progress.mandatoryBucketsHint')}
            </p>
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

      {showCurriculum ? (
        <div id="progress-curriculum">
          <CurriculumGraphSection graph={curriculumGraph!} t={t} />
        </div>
      ) : null}

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
