import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, CheckCircle2 } from 'lucide-react'
import { buildChainRequirementView, type ResolvedChainStep } from '../../lib/chainRequirementSteps'
import {
  buildCourseEquivalenceGroups,
  dedupeEquivalentPoolCourses,
  expandNumbersWithEquivalence,
  isCountedViaEquivalence,
} from '../../lib/courseEquivalence'
import {
  catalogLinkForPool,
  isRequiredCurriculumCourse,
  localizedCourseTitle,
  poolCountedCourseNumbers,
} from '../../lib/electivePools'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'
import { PoolCourseListItem } from './PoolCourseListItem'
import type { CurriculumGraph, ElectiveBucket, RequirementProgressEntry } from '../../types/api'

type ChainRequirementViewProps = {
  pool: ElectiveBucket
  allPools: ElectiveBucket[]
  bucket: RequirementProgressEntry
  requiredCurriculumNumbers: Set<string>
  curriculumGraph?: CurriculumGraph | null
  t: (key: string) => string
}

function StepStatusBadge({ satisfied, t }: { satisfied: boolean; t: (key: string) => string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
        satisfied ? 'bg-emerald-100 text-emerald-800' : 'bg-stone-100 text-stone-600',
      )}
    >
      {satisfied ? <CheckCircle2 className="h-3 w-3" /> : null}
      {satisfied
        ? t('progress.electiveExplorer.chainStepStatus.done')
        : t('progress.electiveExplorer.chainStepStatus.pending')}
    </span>
  )
}

function ChainStepSection({
  step,
  locale,
  countedNumbers,
  equivalenceGroups,
  requiredCurriculumNumbers,
  curriculumGraph,
  t,
}: {
  step: ResolvedChainStep
  locale: 'he' | 'en'
  countedNumbers: Set<string>
  equivalenceGroups: Array<Set<string>>
  requiredCurriculumNumbers: Set<string>
  curriculumGraph?: CurriculumGraph | null
  t: (key: string) => string
}) {
  const visibleCourses = useMemo(
    () =>
      dedupeEquivalentPoolCourses(step.courses, {
        countedNumbers,
        requiredCurriculumNumbers,
        curriculumGraph,
      }),
    [countedNumbers, curriculumGraph, requiredCurriculumNumbers, step.courses],
  )

  return (
    <section
      className="rounded-xl border border-[var(--color-border)] bg-white p-3.5 shadow-sm"
      data-testid={`chain-step-${step.id}`}
    >
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-violet-700">
            {t('progress.electiveExplorer.chainStepHeading')} {step.stepNumber}
          </p>
          <p className="mt-0.5 text-sm font-medium leading-snug">{step.title}</p>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{step.kindLabel}</p>
        </div>
        <StepStatusBadge satisfied={step.satisfied} t={t} />
      </div>

      {step.note ? (
        <p className="mb-3 rounded-lg bg-violet-50/80 px-2.5 py-2 text-xs leading-relaxed text-violet-900/90">
          {step.note}
        </p>
      ) : null}

      {visibleCourses.length ? (
        <ul className="space-y-2">
          {visibleCourses.map((course) => (
            <PoolCourseListItem
              key={course.courseNumber}
              course={course}
              displayTitle={localizedCourseTitle(course, locale)}
              isCounted={isCountedViaEquivalence(
                course.courseNumber,
                countedNumbers,
                equivalenceGroups,
              )}
              isRequiredCurriculum={isRequiredCurriculumCourse(
                course.courseNumber,
                requiredCurriculumNumbers,
              )}
              countedLabel={t('progress.electiveExplorer.counted')}
              requiredLabel={t('progress.electiveExplorer.requiredCourse')}
              compact
            />
          ))}
        </ul>
      ) : (
        <p className="rounded-lg border border-dashed border-[var(--color-border)] px-3 py-4 text-center text-xs text-[var(--color-text-muted)]">
          {t('progress.electiveExplorer.chainStepEmpty')}
        </p>
      )}
    </section>
  )
}

export function ChainRequirementView({
  pool,
  allPools,
  bucket,
  requiredCurriculumNumbers,
  curriculumGraph,
  t,
}: ChainRequirementViewProps) {
  const { locale } = useTranslation()
  const [activeChainId, setActiveChainId] = useState<string | null>(null)

  const bucketCountedNumbers = useMemo(
    () => poolCountedCourseNumbers(pool, bucket, allPools),
    [allPools, bucket, pool],
  )

  const equivalenceGroups = useMemo(
    () =>
      buildCourseEquivalenceGroups({
        curriculumGraph,
        poolCourses: pool.courses,
      }),
    [curriculumGraph, pool.courses],
  )

  const expandedCountedNumbers = useMemo(
    () => expandNumbersWithEquivalence(bucketCountedNumbers, equivalenceGroups),
    [bucketCountedNumbers, equivalenceGroups],
  )

  const view = useMemo(
    () => buildChainRequirementView(pool, t, expandedCountedNumbers),
    [expandedCountedNumbers, pool, t],
  )

  const defaultActiveChainId = useMemo(() => {
    if (view?.layout !== 'pick_one_chain') return null
    return (
      [...view.chains].sort((left, right) => right.satisfiedCount - left.satisfiedCount)[0]?.id ??
      view.chains[0]?.id ??
      null
    )
  }, [view])

  useEffect(() => {
    if (view?.layout !== 'pick_one_chain' || activeChainId) return
    if (defaultActiveChainId) {
      setActiveChainId(defaultActiveChainId)
    }
  }, [activeChainId, defaultActiveChainId, view?.layout])

  if (!view) return null

  const stepSectionProps = {
    locale,
    countedNumbers: bucketCountedNumbers,
    equivalenceGroups,
    requiredCurriculumNumbers,
    curriculumGraph,
    t,
  }

  if (view.layout === 'pick_one_chain') {
    const activeChain =
      view.chains.find((chain) => chain.id === activeChainId) ??
      view.chains.find((chain) => chain.id === defaultActiveChainId) ??
      view.chains[0] ??
      null

    return (
      <div className="space-y-4" data-testid={`chain-requirement-view-${pool.groupId}`}>
        <p className="text-sm leading-relaxed text-[var(--color-text-muted)]">{view.intro}</p>

        <div className="flex flex-wrap gap-2">
          {view.chains.map((chain) => (
            <button
              key={chain.id}
              type="button"
              onClick={() => setActiveChainId(chain.id)}
              className={cn(
                'rounded-full border px-3 py-1.5 text-xs font-medium transition',
                activeChain?.id === chain.id
                  ? 'border-violet-300 bg-violet-100 text-violet-900'
                  : 'border-[var(--color-border)] bg-white text-[var(--color-text-muted)] hover:border-violet-200',
              )}
            >
              {chain.title}
              <span className="ms-1.5 tabular-nums text-[10px] opacity-80">
                {chain.satisfiedCount}/{chain.steps.length}
              </span>
            </button>
          ))}
        </div>

        {activeChain ? (
          <div className="space-y-3">
            {activeChain.steps.map((step) => (
              <ChainStepSection key={step.id} step={step} {...stepSectionProps} />
            ))}
          </div>
        ) : null}

        <div className="flex justify-end pt-1">
          <Link
            to={catalogLinkForPool(pool)}
            className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 text-sm font-medium hover:bg-[var(--color-surface-muted)]"
          >
            <BookOpen className="h-4 w-4" />
            {t('progress.electiveExplorer.openCatalog')}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3" data-testid={`chain-requirement-view-${pool.groupId}`}>
      {view.steps.map((step) => (
        <ChainStepSection key={step.id} step={step} {...stepSectionProps} />
      ))}

      <div className="flex justify-end pt-1">
        <Link
          to={catalogLinkForPool(pool)}
          className="inline-flex h-9 items-center gap-2 rounded-lg border border-[var(--color-border)] px-3 text-sm font-medium hover:bg-[var(--color-surface-muted)]"
        >
          <BookOpen className="h-4 w-4" />
          {t('progress.electiveExplorer.openCatalog')}
        </Link>
      </div>
    </div>
  )
}
