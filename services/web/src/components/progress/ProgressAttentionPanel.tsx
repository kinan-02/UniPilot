import { AlertCircle, ChevronDown } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Badge, Card } from '../ui/Card'
import { CourseChipList } from './ProgressSections'
import {
  actionableIneligibleCredits,
  filterRemainingMandatoryCourses,
  bucketCompletionPercent,
  ineligibleCreditReasonLabel,
} from '../../lib/graduationProgress'
import { catalogSearchLink, interpolateTemplate, localizedBucketTitle } from '../../lib/electivePools'
import { formatCredits, cn } from '../../lib/utils'
import type { CurriculumGraph, GraduationProgress } from '../../types/api'
import type { useTranslation } from '../../i18n'

type TFn = ReturnType<typeof useTranslation>['t']

type ProgressAttentionPanelProps = {
  progress: GraduationProgress
  curriculumGraph?: CurriculumGraph | null
  t: TFn
}

export function ProgressAttentionPanel({ progress, curriculumGraph, t }: ProgressAttentionPanelProps) {
  const remainingMandatory = filterRemainingMandatoryCourses(
    progress.remainingMandatoryCourses,
    progress.completedMandatoryCourses,
    { curriculumGraph, progress },
  )
  const ineligible = actionableIneligibleCredits(progress)
  const missingBuckets = progress.missingRequirements ?? []

  const itemCount = remainingMandatory.length + ineligible.length + missingBuckets.length
  const [expanded, setExpanded] = useState(() => itemCount <= 6)

  if (itemCount === 0) return null

  return (
    <Card
      className="scroll-mt-24 overflow-hidden p-0"
      data-testid="progress-attention-panel"
      id="progress-attention"
    >
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls="progress-attention-details"
        aria-label={t('progress.attention.toggleLabel')}
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center gap-3 border-b border-[var(--color-border)] bg-gradient-to-r from-amber-50/80 via-white to-white px-5 py-4 text-start transition hover:bg-amber-50/40"
      >
        <AlertCircle className="h-5 w-5 shrink-0 text-amber-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{t('progress.attention.title')}</p>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
            {t('progress.attention.subtitle')}
          </p>
        </div>
        <Badge tone="warning">{itemCount}</Badge>
        <ChevronDown
          className={cn(
            'h-5 w-5 shrink-0 text-[var(--color-text-muted)] transition-transform',
            expanded && 'rotate-180',
          )}
          aria-hidden
        />
      </button>

      {!expanded ? (
        <div className="flex flex-wrap gap-2 px-5 py-3">
          {remainingMandatory.length ? (
            <span className="rounded-full bg-amber-100 px-2.5 py-1 text-xs font-medium text-amber-900">
              {interpolateTemplate(t('progress.attention.collapsedMandatory'), {
                count: remainingMandatory.length,
              })}
            </span>
          ) : null}
          {missingBuckets.length ? (
            <span className="rounded-full bg-sky-100 px-2.5 py-1 text-xs font-medium text-sky-900">
              {interpolateTemplate(t('progress.attention.collapsedBuckets'), {
                count: missingBuckets.length,
              })}
            </span>
          ) : null}
          {ineligible.length ? (
            <span className="rounded-full bg-red-100 px-2.5 py-1 text-xs font-medium text-red-900">
              {interpolateTemplate(t('progress.attention.collapsedIneligible'), {
                count: ineligible.length,
              })}
            </span>
          ) : null}
        </div>
      ) : null}

      {expanded ? (
        <div id="progress-attention-details" className="divide-y divide-[var(--color-border)]">
          {remainingMandatory.length ? (
            <section className="px-5 py-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t('progress.remainingMandatory')}
                </h3>
                <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
                  {remainingMandatory.length}
                </span>
              </div>
              <CourseChipList courses={remainingMandatory} />
            </section>
          ) : null}

          {missingBuckets.length ? (
            <section className="px-5 py-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t('progress.missingRequirements')}
                </h3>
                <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
                  {missingBuckets.length}
                </span>
              </div>
              <ul className="space-y-2">
                {missingBuckets.map((entry) => {
                  const percent = bucketCompletionPercent(
                    entry.creditsCompleted,
                    entry.creditsRequired,
                  )
                  return (
                    <li
                      key={entry.requirementGroupId}
                      className="rounded-xl border border-[var(--color-border)] bg-white/80 px-3 py-2.5"
                    >
                      <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                        <span className="truncate font-medium">
                          {localizedBucketTitle(entry, t)}
                        </span>
                        <span className="shrink-0 tabular-nums text-xs text-[var(--color-text-muted)]">
                          {formatCredits(entry.creditsCompleted)} /{' '}
                          {formatCredits(entry.creditsRequired)}
                        </span>
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-stone-100">
                        <div
                          className="h-full rounded-full bg-[var(--color-primary)]"
                          style={{ width: `${percent}%` }}
                        />
                      </div>
                    </li>
                  )
                })}
              </ul>
            </section>
          ) : null}

          {ineligible.length ? (
            <section className="px-5 py-4">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t('progress.ineligibleCredits')}
                </h3>
                <span className="text-xs tabular-nums text-[var(--color-text-muted)]">
                  {ineligible.length}
                </span>
              </div>
              <ul className="divide-y divide-[var(--color-border)] overflow-hidden rounded-xl border border-red-100 bg-red-50/40">
                {ineligible.map((entry) => {
                  const courseNumber = entry.courseNumber ?? entry.courseId.slice(-8)
                  return (
                    <li
                      key={entry.courseId}
                      className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
                    >
                      <span className="font-mono text-xs font-medium text-red-900">{courseNumber}</span>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-xs text-[var(--color-text-muted)]">
                          {formatCredits(entry.creditsEarned)} ·{' '}
                          {ineligibleCreditReasonLabel(entry.reason, t)}
                        </span>
                        <Link
                          to="/transcript"
                          className="text-xs font-medium text-[var(--color-primary)] hover:underline"
                        >
                          {t('progress.ineligibleActions.viewTranscript')}
                        </Link>
                        {entry.courseNumber ? (
                          <Link
                            to={catalogSearchLink(entry.courseNumber)}
                            className="text-xs font-medium text-[var(--color-primary)] hover:underline"
                          >
                            {t('progress.ineligibleActions.viewCatalog')}
                          </Link>
                        ) : null}
                      </div>
                    </li>
                  )
                })}
              </ul>
              <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                {t('progress.ineligibleCreditsHint')}
              </p>
            </section>
          ) : null}
        </div>
      ) : null}
    </Card>
  )
}
