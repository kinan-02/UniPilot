import { Link, useSearchParams } from 'react-router-dom'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'
import { progressApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import {
  ProgressEmptyTranscriptHint,
} from '../components/progress/ProgressSections'
import { ProgressBucketSection } from '../components/progress/ProgressBucketSection'
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
import {
  buildFullTranscriptCourseNumbers,
  buildRequiredCurriculumCourseNumbers,
} from '../lib/electivePools'
import {
  countAttentionItems,
  apiRemainingMandatoryCourses,
  hasActionableGaps,
  overlapIneligibleCredits,
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
      }),
    [
      curriculumQuery.data?.curriculumGraph,
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

  const { mandatory, elective, generalTechnion } = partitionRequirementBuckets(
    progress.requirementProgress,
  )
  const showTranscriptHint =
    progress.statusSummary === 'not_started' || progress.completedCredits <= 0
  const curriculumGraph = curriculumQuery.data?.curriculumGraph
  const curriculumLoadError =
    curriculumQuery.isError && curriculumQuery.error instanceof Error
      ? curriculumQuery.error.message
      : null
  const showAttention =
    hasActionableGaps(progress) || overlapIneligibleCredits(progress).length > 0
  const attentionCount = countAttentionItems(progress)
  const showCurriculum = Boolean(curriculumGraph)
  const showPools =
    !curriculumQuery.isLoading || curriculumQuery.data
      ? electivePools.length > 0
      : false
  const showCelebration =
    !showAttention &&
    (progress.statusSummary === 'complete' ||
      progress.statusSummary === 'mandatory_requirements_met')
  const mandatoryRemainingCount = apiRemainingMandatoryCourses(progress).length
  const progressAdvisories = progress.advisoryWarnings ?? []
  const curriculumAdvisories = curriculumGraph?.advisories ?? []
  const mergedAdvisoryCodes = new Set<string>()
  const mergedAdvisories = [...progressAdvisories, ...curriculumAdvisories].filter((advisory) => {
    if (mergedAdvisoryCodes.has(advisory.code)) return false
    mergedAdvisoryCodes.add(advisory.code)
    return true
  })
  const navSections = [
    { id: 'progress-overview', label: t('progress.nav.overview') },
    ...(showAttention
      ? [{ id: 'progress-attention', label: t('progress.nav.attention') }]
      : []),
    ...(showCurriculum || curriculumQuery.isError
      ? [{ id: 'progress-curriculum', label: t('progress.nav.curriculum') }]
      : []),
    ...(mandatory.length
      ? [{ id: 'progress-mandatory', label: t('progress.nav.mandatory') }]
      : []),
    ...(elective.length ? [{ id: 'progress-elective', label: t('progress.nav.elective') }] : []),
    ...(generalTechnion.length
      ? [{ id: 'progress-general-technion', label: t('progress.nav.generalTechnion') }]
      : []),
    ...(showPools ? [{ id: 'elective-pools-panel', label: t('progress.nav.pools') }] : []),
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
        t={t}
      />

      <ProgressPageNav sections={navSections} t={t} />

      {showCelebration ? (
        <ProgressCompletionCelebration progress={progress} statusLabel={statusLabel} t={t} />
      ) : null}

      {showAttention ? (
        <ProgressAttentionPanel progress={progress} t={t} />
      ) : null}

      {showCurriculum ? (
        <div id="progress-curriculum">
          <CurriculumGraphSection graph={curriculumGraph!} t={t} />
        </div>
      ) : curriculumQuery.isError ? (
        <Card className="scroll-mt-24 border-dashed" id="progress-curriculum">
          <h2 className="text-lg font-semibold">{t('progress.curriculum.title')}</h2>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">
            {t('progress.curriculum.loadFailed')}
          </p>
          {curriculumLoadError ? (
            <p className="mt-2 text-sm text-amber-900 text-pretty">{curriculumLoadError}</p>
          ) : null}
        </Card>
      ) : null}

      {mandatory.length ? (
        <ProgressBucketSection
          id="progress-mandatory"
          title={t('progress.mandatoryBuckets')}
          hint={t('progress.mandatoryBucketsHint')}
          aggregateLabel={t('progress.mandatoryAggregate')}
          aggregateHint={t('progress.mandatoryAggregateHint')}
          buckets={mandatory}
          electivePools={electivePools}
          curriculumGraph={curriculumGraph}
          onExplorePool={electivePools.length ? handleExplorePool : undefined}
          t={t}
        />
      ) : null}

      {elective.length ? (
        <ProgressBucketSection
          id="progress-elective"
          title={t('progress.electiveBuckets')}
          hint={t('progress.electiveBucketsHint')}
          buckets={elective}
          electivePools={electivePools}
          curriculumGraph={curriculumGraph}
          onExplorePool={electivePools.length ? handleExplorePool : undefined}
          t={t}
        />
      ) : null}

      {generalTechnion.length ? (
        <ProgressBucketSection
          id="progress-general-technion"
          title={t('progress.generalTechnionBuckets')}
          hint={t('progress.generalTechnionBucketsHint')}
          buckets={generalTechnion}
          electivePools={electivePools}
          curriculumGraph={curriculumGraph}
          onExplorePool={electivePools.length ? handleExplorePool : undefined}
          t={t}
        />
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
      ) : null}

      {mergedAdvisories.length ? (
        <Card className="scroll-mt-24 border-sky-200/80 bg-sky-50/50" id="progress-advisories">
          <h2 className="text-sm font-semibold text-sky-950">{t('progress.curriculumAdvisories')}</h2>
          <ul className="mt-2 space-y-2">
            {mergedAdvisories.map((advisory) => (
              <li key={advisory.code} className="text-sm text-sky-900 text-pretty">
                {advisory.message}
              </li>
            ))}
          </ul>
        </Card>
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
