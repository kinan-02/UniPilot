import { Link } from 'react-router-dom'
import { AlertTriangle, GraduationCap, Target } from 'lucide-react'
import { AgentSection } from './AgentSection'

type DataQualityPayload = {
  warnings?: string[]
  ok?: boolean
}

type AgentPathContextPanelProps = {
  trackSlug?: string
  planSemesterCode?: string
  completedCourseCount?: number
  priorityCourses: string[]
  creditsRemaining?: number | null
  remainingMandatoryCount?: number | null
  dataQuality?: DataQualityPayload | null
  contextSource?: string
  planningSource?: string
  title: string
  trackLabel: string
  priorityLabel: string
  creditsRemainingLabel: string
  mandatoryRemainingLabel: string
  viewProgressLabel: string
  semesterLabel: string
  completedCoursesLabel: string
  dataQualityTitle: string
  dataQualityHint: string
  contextSourceLabel: string
  planningSourceLabel: string
  warningLabel: (code: string) => string
}

export function AgentPathContextPanel({
  trackSlug,
  planSemesterCode,
  completedCourseCount,
  priorityCourses,
  creditsRemaining,
  remainingMandatoryCount,
  dataQuality,
  contextSource,
  planningSource,
  title,
  trackLabel,
  priorityLabel,
  creditsRemainingLabel,
  mandatoryRemainingLabel,
  viewProgressLabel,
  semesterLabel,
  completedCoursesLabel,
  dataQualityTitle,
  dataQualityHint,
  contextSourceLabel,
  planningSourceLabel,
  warningLabel,
}: AgentPathContextPanelProps) {
  const warnings = dataQuality?.warnings ?? []
  const hasWarnings = warnings.length > 0
  const showContextSource = contextSource === 'mongo_fallback'
  const showPlanningSource = planningSource === 'progress_bundle'
  const hasPathDetails =
    Boolean(trackSlug) ||
    Boolean(planSemesterCode) ||
    (completedCourseCount ?? 0) > 0 ||
    priorityCourses.length > 0 ||
    showContextSource ||
    showPlanningSource

  if (!hasPathDetails && !hasWarnings) return null

  return (
    <AgentSection title={title} testId="agent-sessions-path-context" accent="success">
      <div className="overflow-hidden rounded-xl border border-emerald-200/80 bg-gradient-to-br from-emerald-50/90 via-white to-white">
        <div className="space-y-4 p-4">
        {hasWarnings ? (
          <div
            className="rounded-xl border border-amber-200 bg-amber-50/80 px-3 py-3 text-sm text-amber-950"
            data-testid="agent-sessions-data-quality"
          >
            <p className="flex items-center gap-2 font-medium">
              <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
              {dataQualityTitle}
            </p>
            <p className="mt-1 text-xs text-amber-900/90">{dataQualityHint}</p>
            <ul className="mt-2 list-disc space-y-1 ps-5 text-xs">
              {warnings.map((code) => (
                <li key={code}>{warningLabel(code)}</li>
              ))}
            </ul>
          </div>
        ) : null}

        {showContextSource ? (
          <p className="text-xs text-amber-900/90" data-testid="agent-sessions-context-source">
            {contextSourceLabel}
          </p>
        ) : null}

        {showPlanningSource ? (
          <p className="text-xs text-emerald-900/90" data-testid="agent-sessions-planning-source">
            {planningSourceLabel}
          </p>
        ) : null}

        {trackSlug ? (
          <p className="flex items-center gap-2 text-[var(--color-text-muted)]">
            <GraduationCap className="h-4 w-4 shrink-0" aria-hidden />
            {trackLabel}
          </p>
        ) : null}

        {planSemesterCode || (completedCourseCount ?? 0) > 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {planSemesterCode ? (
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2.5">
                <p className="text-xs font-medium text-[var(--color-text-muted)]">{semesterLabel}</p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{planSemesterCode}</p>
              </div>
            ) : null}
            {(completedCourseCount ?? 0) > 0 ? (
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2.5">
                <p className="text-xs font-medium text-[var(--color-text-muted)]">
                  {completedCoursesLabel}
                </p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{completedCourseCount}</p>
              </div>
            ) : null}
          </div>
        ) : null}

        {(creditsRemaining != null || remainingMandatoryCount != null) ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {remainingMandatoryCount != null ? (
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2.5">
                <p className="text-xs font-medium text-[var(--color-text-muted)]">
                  {mandatoryRemainingLabel}
                </p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{remainingMandatoryCount}</p>
              </div>
            ) : null}
            {creditsRemaining != null ? (
              <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2.5">
                <p className="text-xs font-medium text-[var(--color-text-muted)]">
                  {creditsRemainingLabel}
                </p>
                <p className="mt-1 text-lg font-semibold tabular-nums">{creditsRemaining}</p>
              </div>
            ) : null}
          </div>
        ) : null}

        {priorityCourses.length > 0 ? (
          <div>
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              <Target className="h-3.5 w-3.5" aria-hidden />
              {priorityLabel}
            </p>
            <div className="flex flex-wrap gap-2">
              {priorityCourses.slice(0, 10).map((courseId) => (
                <Link
                  key={courseId}
                  to={`/catalog?course=${courseId}`}
                  className="rounded-full border border-emerald-200 bg-emerald-50/80 px-3 py-1 font-mono text-xs font-medium text-emerald-900 transition hover:border-emerald-300"
                >
                  {courseId}
                </Link>
              ))}
            </div>
          </div>
        ) : null}

        <Link
          to="/progress"
          className="inline-flex text-xs font-medium text-[var(--color-primary)] underline-offset-2 hover:underline"
        >
          {viewProgressLabel}
        </Link>
        </div>
      </div>
    </AgentSection>
  )
}
