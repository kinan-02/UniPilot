import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { agentSessionsApi } from '../api/endpoints'
import { getApiBaseUrl } from '../lib/api'
import { AgentActiveSessionHeader } from '../components/agents/AgentActiveSessionHeader'
import { AgentActionBar } from '../components/agents/AgentActionBar'
import { AgentCollapsibleSection } from '../components/agents/AgentCollapsibleSection'
import { AgentComposePanel } from '../components/agents/AgentComposePanel'
import { AgentHistoryPanel } from '../components/agents/AgentHistoryPanel'
import { AgentLivePanel } from '../components/agents/AgentLivePanel'
import { AgentPathContextPanel } from '../components/agents/AgentPathContextPanel'
import { AgentPlanMetrics } from '../components/agents/AgentPlanMetrics'
import { AgentRecommendationHero } from '../components/agents/AgentRecommendationHero'
import { AgentScheduleBoard } from '../components/agents/AgentScheduleBoard'
import { AgentSessionNav } from '../components/agents/AgentSessionNav'
import { AgentSection } from '../components/agents/AgentSection'
import { AgentTranscriptTimeline } from '../components/agents/AgentTranscriptTimeline'
import { AgentUtilityBreakdown } from '../components/agents/AgentUtilityBreakdown'
import { AgentWorkflowStepper } from '../components/agents/AgentWorkflowStepper'
import {
  ACTIVE_STATUSES,
  formatAgentRole,
  resolveWorkflowStep,
  statusTone,
} from '../components/agents/agentSessionUtils'
import { Card, EmptyState, PageHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { useTranslation } from '../i18n'
import type { AgentSession, AgentTurn, MasScheduleCourse } from '../types/api'

function effectiveDecision(session: AgentSession): Record<string, unknown> {
  const override = session.overriddenDecision
  if (override && Array.isArray(override.course_ids) && override.course_ids.length > 0) {
    return override
  }
  return session.finalDecision ?? {}
}

function scheduleCourses(decision: Record<string, unknown>): MasScheduleCourse[] {
  const schedule = decision.schedule
  if (!schedule || typeof schedule !== 'object') return []
  const courses = (schedule as { courses?: unknown }).courses
  if (!Array.isArray(courses)) return []
  return courses.filter((course): course is MasScheduleCourse => {
    return Boolean(course && typeof course === 'object' && 'courseId' in course)
  })
}

function reasoningTraceFromTurn(turn: AgentTurn): Record<string, unknown> | null {
  const trace = turn.payload?.reasoningTrace
  return trace && typeof trace === 'object' ? (trace as Record<string, unknown>) : null
}

function ReasoningTracePanel({
  trace,
  t,
}: {
  trace: Record<string, unknown>
  t: (key: string, values?: Record<string, string | number>) => string
}) {
  const kind = String(trace.kind ?? 'unknown')

  if (kind === 'planner_tool_loop') {
    const steps = Array.isArray(trace.steps) ? trace.steps : []
    return (
      <details
        className="mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-3 text-xs"
        data-testid="reasoning-trace"
      >
        <summary className="cursor-pointer font-medium text-[var(--color-text)]">
          {t('agentSessions.reasoningTitle')}
        </summary>
        <p className="mt-2 text-[var(--color-text-muted)]">
          {t('agentSessions.reasoningToolLoopStatus', { status: String(trace.status ?? 'unknown') })}
        </p>
        {typeof trace.reasoning === 'string' && trace.reasoning ? (
          <p className="mt-2 whitespace-pre-wrap">{trace.reasoning}</p>
        ) : null}
        <ol className="mt-3 space-y-2">
          {steps.map((step, index) => {
            if (!step || typeof step !== 'object') return null
            const record = step as Record<string, unknown>
            const toolCalls = Array.isArray(record.tool_calls) ? record.tool_calls : []
            const blocks = Array.isArray(record.retrieved_blocks) ? record.retrieved_blocks : []
            return (
              <li
                key={`step-${String(record.iteration ?? index)}`}
                className="rounded-lg border border-[var(--color-border)] bg-white p-2"
              >
                <p className="font-medium">
                  {t('agentSessions.reasoningStep', { step: String(record.iteration ?? index + 1) })}
                </p>
                {typeof record.content === 'string' && record.content ? (
                  <p className="mt-1 whitespace-pre-wrap text-[var(--color-text-muted)]">{record.content}</p>
                ) : null}
                {toolCalls.length > 0 ? (
                  <ul className="mt-1 list-disc ps-4 text-[var(--color-text-muted)]">
                    {toolCalls.map((call, callIndex) => {
                      if (!call || typeof call !== 'object') return null
                      const name = String((call as { name?: unknown }).name ?? 'tool')
                      return <li key={`${name}-${callIndex}`}>{name}</li>
                    })}
                  </ul>
                ) : null}
                {blocks.length > 0 ? (
                  <p className="mt-1 text-[var(--color-text-muted)]">
                    {t('agentSessions.reasoningBlocks', { count: blocks.length })}
                  </p>
                ) : null}
                {record.proposal && typeof record.proposal === 'object' ? (
                  <p className="mt-1 font-medium">
                    {t('agentSessions.reasoningProposal', {
                      courses: String(
                        ((record.proposal as { course_ids?: unknown }).course_ids as string[] | undefined)?.join(', ') ??
                          '—',
                      ),
                    })}
                  </p>
                ) : null}
              </li>
            )
          })}
        </ol>
      </details>
    )
  }

  return (
    <details
      className="mt-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-3 text-xs"
      data-testid="reasoning-trace"
    >
      <summary className="cursor-pointer font-medium text-[var(--color-text)]">
        {t('agentSessions.reasoningTitle')}
      </summary>
      <p className="mt-2 text-[var(--color-text-muted)]">{t('agentSessions.reasoningKind', { kind })}</p>
      {typeof trace.reasoning === 'string' && trace.reasoning ? (
        <p className="mt-2 whitespace-pre-wrap">{trace.reasoning}</p>
      ) : null}
      {typeof trace.intent === 'string' ? (
        <p className="mt-1">{t('agentSessions.reasoningIntent', { intent: trace.intent })}</p>
      ) : null}
      {trace.confidence != null ? (
        <p className="mt-1">{t('agentSessions.reasoningConfidence', { confidence: String(trace.confidence) })}</p>
      ) : null}
      {typeof trace.clarification_question === 'string' && trace.clarification_question ? (
        <p className="mt-2 whitespace-pre-wrap">{trace.clarification_question}</p>
      ) : null}
      {trace.progressScore != null ? (
        <p className="mt-1">
          {t('agentSessions.reasoningProgressScore', { score: String(trace.progressScore) })}
        </p>
      ) : null}
      {trace.unlockCount != null ? (
        <p className="mt-1">
          {t('agentSessions.reasoningUnlockCount', { count: String(trace.unlockCount) })}
        </p>
      ) : null}
      {trace.critiqueCount != null ? (
        <p className="mt-1">
          {t('agentSessions.reasoningCritiqueCount', { count: String(trace.critiqueCount) })}
        </p>
      ) : null}
      {trace.violationCount != null ? (
        <p className="mt-1">
          {t('agentSessions.reasoningViolationCount', { count: String(trace.violationCount) })}
        </p>
      ) : null}
      {trace.approved === true ? (
        <p className="mt-1 text-emerald-700">{t('agentSessions.reasoningApproved')}</p>
      ) : null}
      {trace.approved === false ? (
        <p className="mt-1 text-rose-700">{t('agentSessions.reasoningRejected')}</p>
      ) : null}
      {trace.evidence && typeof trace.evidence === 'object' ? (
        <p className="mt-1 text-[var(--color-text-muted)]">
          {(() => {
            const evidence = trace.evidence as Record<string, unknown>
            const total = evidence.totalCredits
            const max = evidence.maxCredits
            if (total != null && max != null) {
              return t('agentSessions.reasoningCreditLoad', {
                total: String(total),
                max: String(max),
              })
            }
            return null
          })()}
        </p>
      ) : null}
      {Array.isArray(trace.critiques) && trace.critiques.length > 0 ? (
        <ul className="mt-2 list-disc ps-4">
          {trace.critiques.map((item, index) => {
            if (!item || typeof item !== 'object') return null
            const critique = item as { type?: string; message?: string }
            return (
              <li key={`critique-${String(critique.type ?? index)}`}>
                {String(critique.message ?? critique.type ?? '')}
              </li>
            )
          })}
        </ul>
      ) : null}
      {Array.isArray(trace.variants) && trace.variants.length > 0 ? (
        <ul className="mt-2 space-y-2">
          {trace.variants.map((item, index) => {
            if (!item || typeof item !== 'object') return null
            const variant = item as Record<string, unknown>
            return (
              <li
                key={`variant-${String(variant.variant ?? index)}`}
                className="rounded-lg border border-[var(--color-border)] bg-white p-2"
              >
                <p className="font-medium">{String(variant.variant ?? `variant ${index + 1}`)}</p>
                {variant.progressScore != null ? (
                  <p className="text-[var(--color-text-muted)]">
                    {t('agentSessions.reasoningProgressScore', { score: String(variant.progressScore) })}
                  </p>
                ) : null}
              </li>
            )
          })}
        </ul>
      ) : null}
      {Array.isArray(trace.violations) && trace.violations.length > 0 ? (
        <ul className="mt-2 list-disc ps-4">
          {trace.violations.map((item) => (
            <li key={String(item)}>{String(item)}</li>
          ))}
        </ul>
      ) : null}
    </details>
  )
}

function TranscriptReasoning({
  turn,
  t,
}: {
  turn: AgentTurn
  t: (key: string, values?: Record<string, string | number>) => string
}) {
  const reasoningTrace = reasoningTraceFromTurn(turn)
  if (!reasoningTrace) return null
  return <ReasoningTracePanel trace={reasoningTrace} t={t} />
}

type SessionResultProps = {
  session: AgentSession
  replayEvents?: Array<Record<string, unknown>>
  whyAnswer?: {
    answer: string
    citations: Array<Record<string, unknown>>
    topics: string[]
  } | null
  onApprove: () => void
  onApply: () => void
  onClarify?: (clarification: string) => void
  onAskWhy?: (question: string) => void
  onSecondOpinion?: (utilityProfile: 'balanced' | 'risk_averse' | 'aggressive') => void
  approving: boolean
  applying: boolean
  clarifying?: boolean
  askingWhy?: boolean
  secondOpinionLoading?: boolean
  applyError: string | null
  clarifyError?: string | null
  whyError?: string | null
  secondOpinionError?: string | null
}

function SessionResult({
  session,
  replayEvents = [],
  whyAnswer = null,
  onApprove,
  onApply,
  onClarify,
  onAskWhy,
  onSecondOpinion,
  approving,
  applying,
  clarifying = false,
  askingWhy = false,
  secondOpinionLoading = false,
  applyError,
  clarifyError = null,
  whyError = null,
  secondOpinionError = null,
}: SessionResultProps) {
  const { t } = useTranslation()
  const [clarificationAnswer, setClarificationAnswer] = useState('')
  const [whyQuestion, setWhyQuestion] = useState('')
  const decision = effectiveDecision(session)
  const courseIds = Array.isArray(decision.course_ids) ? (decision.course_ids as string[]) : []
  const softCritiques = Array.isArray(decision.softCritiques)
    ? (decision.softCritiques as Array<Record<string, unknown>>)
    : []
  const utility = session.utilityBreakdown as Record<string, unknown> | undefined
  const courses = scheduleCourses(decision)
  const semesterLabel =
    typeof decision.semesterLabel === 'string'
      ? decision.semesterLabel
      : typeof (decision.schedule as { semesterLabel?: string } | undefined)?.semesterLabel === 'string'
        ? (decision.schedule as { semesterLabel: string }).semesterLabel
        : null
  const isApproved = Boolean(session.approvedAt)
  const isApplied = Boolean(session.appliedPlanId)
  const studentSummary = decision.studentSummary as
    | { headline?: string; rationale?: string; trade_offs?: string[] }
    | undefined
  const clarificationQuestion =
    typeof decision.clarificationQuestion === 'string' ? decision.clarificationQuestion : null
  const whatIf = decision.whatIf as Record<string, unknown> | undefined
  const whatIfComparison = decision.whatIfComparison as
    | {
        baselineCompletedCourses?: string[]
        scenarioCompletedCourses?: string[]
      }
    | undefined
  const counterfactuals = Array.isArray(decision.counterfactualExplanations)
    ? (decision.counterfactualExplanations as Array<Record<string, unknown>>)
    : []
  const redTeamReview = decision.redTeamReview as
    | {
        severity?: string
        attackCount?: number
        attacks?: Array<{ type?: string; severity?: string; message?: string }>
      }
    | undefined
  const sessionLineage = decision.sessionLineage as
    | {
        kind?: string
        sourceSessionId?: string
        utilityProfile?: string
        clarificationCount?: number
      }
    | undefined
  const policyAnswer =
    decision.vertical === 'policy_qa' && typeof decision.answer === 'string'
      ? decision.answer
      : null
  const policyCitations = Array.isArray(decision.citations)
    ? (decision.citations as Array<Record<string, unknown>>)
    : []
  const pathContext = decision.pathContext as
    | {
        trackSlug?: string
        planSemesterCode?: string
        priorityRemainingCourses?: string[]
        remainingMandatoryCount?: number
        creditsRemaining?: number
        completedCourseCount?: number
        contextSource?: string
        planningSource?: string
        planningReady?: boolean
        dataQuality?: { warnings?: string[]; ok?: boolean }
      }
    | undefined

  const pathDataQualityWarnings = pathContext?.dataQuality?.warnings ?? []
  const showPathContextPanel =
    Boolean(pathContext) &&
    ((pathContext?.priorityRemainingCourses?.length ?? 0) > 0 ||
      Boolean(pathContext?.trackSlug) ||
      Boolean(pathContext?.planSemesterCode) ||
      (pathContext?.completedCourseCount ?? 0) > 0 ||
      pathDataQualityWarnings.length > 0 ||
      pathContext?.contextSource === 'mongo_fallback' ||
      pathContext?.planningSource === 'progress_bundle')

  const pathDataQualityLabel = (code: string) => {
    const key = `agentSessions.pathDataQuality_${code}` as const
    const translated = t(key)
    return translated === key ? code.replace(/_/g, ' ') : translated
  }

  const utilityComponents =
    utility?.components && typeof utility.components === 'object'
      ? (utility.components as Record<string, number>)
      : null

  const actionLabel = (action: string) => {
    const labels: Record<string, string> = {
      propose: t('agentSessions.actionPropose'),
      revise: t('agentSessions.actionRevise'),
      veto: t('agentSessions.actionVeto'),
      commit: t('agentSessions.actionCommit'),
      review: t('agentSessions.actionReview'),
    }
    return labels[action] ?? action.replace(/_/g, ' ')
  }

  const hasAdvancedAnalysis =
    counterfactuals.length > 0 ||
    (redTeamReview?.attackCount ?? 0) > 0 ||
    replayEvents.length > 0

  const sessionNavSections = useMemo(() => {
    const sections: Array<{ id: string; label: string }> = [
      { id: 'agent-session-overview', label: t('agentSessions.navOverview') },
    ]
    if (showPathContextPanel) {
      sections.push({ id: 'agent-session-path', label: t('agentSessions.navPath') })
    }
    if (courseIds.length > 0) {
      sections.push({ id: 'agent-session-schedule', label: t('agentSessions.navSchedule') })
      sections.push({ id: 'agent-session-score', label: t('agentSessions.navScore') })
    }
    sections.push({ id: 'agent-session-transcript', label: t('agentSessions.navTranscript') })
    if (onAskWhy) {
      sections.push({ id: 'agent-session-why', label: t('agentSessions.navWhy') })
    }
    if (hasAdvancedAnalysis) {
      sections.push({ id: 'agent-session-advanced', label: t('agentSessions.navAdvanced') })
    }
    return sections
  }, [courseIds.length, hasAdvancedAnalysis, onAskWhy, showPathContextPanel, t])

  return (
    <div className="space-y-5">
      <AgentSessionNav sections={sessionNavSections} t={t} />

      <div id="agent-session-overview" className="scroll-mt-24 space-y-5">
      {(studentSummary?.headline || courseIds.length > 0) && !policyAnswer ? (
        <>
          <AgentRecommendationHero
            headline={studentSummary?.headline}
            rationale={studentSummary?.rationale}
            courseIds={courseIds}
            courseDetails={courses.map((course) => ({
              id: course.courseId,
              title: course.title,
              credits: course.credits,
            }))}
            semesterLabel={semesterLabel ? t('agentSessions.semesterLabel', { label: semesterLabel }) : null}
            utilityScore={utility?.utility != null ? String(utility.utility) : null}
            creditsLabel={t('agentSessions.utilityShortLabel')}
            utilityScoreLabel={
              utility?.utility != null
                ? t('agentSessions.utilityScore', { score: String(utility.utility) })
                : undefined
            }
            recommendedLabel={t('agentSessions.recommendedPlanLabel')}
            viewCourseLabel={t('agentSessions.viewCourse')}
            summaryTestId={studentSummary?.headline ? 'agent-sessions-summary' : undefined}
          />
          {courseIds.length > 0 ? (
            <AgentPlanMetrics
              courseCount={courseIds.length}
              totalCredits={
                typeof utility?.totalCredits === 'number' || typeof utility?.totalCredits === 'string'
                  ? utility.totalCredits
                  : '—'
              }
              utilityScore={utility?.utility != null ? Number(utility.utility) : null}
              coursesLabel={t('agentSessions.metricsCourses')}
              creditsLabel={t('agentSessions.metricsCredits')}
              utilityLabel={t('agentSessions.metricsUtility')}
            />
          ) : null}
        </>
      ) : null}
      </div>

      {showPathContextPanel ? (
        <div id="agent-session-path" className="scroll-mt-24">
        <AgentPathContextPanel
          trackSlug={pathContext?.trackSlug}
          planSemesterCode={pathContext?.planSemesterCode}
          completedCourseCount={pathContext?.completedCourseCount}
          priorityCourses={pathContext?.priorityRemainingCourses ?? []}
          creditsRemaining={pathContext?.creditsRemaining}
          remainingMandatoryCount={pathContext?.remainingMandatoryCount}
          dataQuality={pathContext?.dataQuality}
          contextSource={pathContext?.contextSource}
          planningSource={pathContext?.planningSource}
          title={t('agentSessions.pathTitle')}
          trackLabel={
            pathContext?.trackSlug
              ? t('agentSessions.pathTrack', { track: pathContext.trackSlug })
              : ''
          }
          priorityLabel={t('agentSessions.pathPriorityHeading')}
          creditsRemainingLabel={t('agentSessions.pathCreditsRemaining')}
          mandatoryRemainingLabel={t('agentSessions.pathMandatoryRemaining')}
          viewProgressLabel={t('agentSessions.viewProgressLink')}
          semesterLabel={t('agentSessions.pathSemesterCode')}
          completedCoursesLabel={t('agentSessions.pathCompletedCourses')}
          dataQualityTitle={t('agentSessions.pathDataQualityTitle')}
          dataQualityHint={t('agentSessions.pathDataQualityHint')}
          contextSourceLabel={t('agentSessions.pathContextSource')}
          planningSourceLabel={t('agentSessions.pathPlanningSource')}
          warningLabel={pathDataQualityLabel}
        />
        </div>
      ) : null}

      {policyAnswer ? (
        <AgentSection title={t('agentSessions.policyTitle')} testId="agent-sessions-policy-answer" accent="primary">
          <p className="whitespace-pre-wrap text-[var(--color-text-muted)]">{policyAnswer}</p>
          {policyCitations.length > 0 ? (
            <ul className="mt-3 space-y-2 text-xs text-[var(--color-text-muted)]">
              {policyCitations.map((citation, index) => (
                <li
                  key={`${String(citation.slug)}-${index}`}
                  className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-3 py-2"
                >
                  <span className="font-medium text-[var(--color-text)]">
                    {String(citation.title ?? citation.slug ?? 'source')}
                  </span>
                  <p className="mt-1">{String(citation.excerpt ?? '')}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </AgentSection>
      ) : null}

      {sessionLineage ? (
        <AgentSection title={t('agentSessions.lineageTitle')} testId="agent-sessions-lineage" accent="info">
          {sessionLineage.kind === 'second_opinion' ? (
            <p className="text-[var(--color-text-muted)]">
              {t('agentSessions.lineageSecondOpinion', {
                profile: String(sessionLineage.utilityProfile ?? 'balanced'),
                source: String(sessionLineage.sourceSessionId ?? '—'),
              })}
            </p>
          ) : null}
          {sessionLineage.kind === 'clarification_resume' ? (
            <p className="text-[var(--color-text-muted)]">
              {t('agentSessions.lineageClarification', {
                count: String(sessionLineage.clarificationCount ?? 0),
              })}
            </p>
          ) : null}
        </AgentSection>
      ) : null}

      {whatIf ? (
        <AgentSection title={t('agentSessions.whatIfTitle')} testId="agent-sessions-what-if" accent="info">
          <p className="text-[var(--color-text-muted)]">
            {t('agentSessions.whatIfScenario', { scenario: String(whatIf.scenario ?? 'unknown') })}
          </p>
          {whatIfComparison ? (
            <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-3">
                <p className="font-medium">{t('agentSessions.whatIfBaseline')}</p>
                <p className="mt-1 text-[var(--color-text-muted)]">
                  {(whatIfComparison.baselineCompletedCourses ?? []).join(', ') || '—'}
                </p>
              </div>
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-3">
                <p className="font-medium">{t('agentSessions.whatIfScenarioLabel')}</p>
                <p className="mt-1 text-[var(--color-text-muted)]">
                  {(whatIfComparison.scenarioCompletedCourses ?? []).join(', ') || '—'}
                </p>
              </div>
            </div>
          ) : null}
        </AgentSection>
      ) : null}

      {session.status === 'awaiting_clarification' && clarificationQuestion ? (
        <AgentSection
          title={t('agentSessions.clarificationTitle')}
          testId="agent-sessions-clarification"
          accent="warning"
        >
          <p className="text-[var(--color-text-muted)]">{clarificationQuestion}</p>
          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              const trimmed = clarificationAnswer.trim()
              if (!trimmed || clarifying || !onClarify) return
              onClarify(trimmed)
            }}
          >
            <textarea
              value={clarificationAnswer}
              onChange={(event) => setClarificationAnswer(event.target.value)}
              placeholder={t('agentSessions.clarificationPlaceholder')}
              rows={3}
              className="w-full rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20"
              data-testid="agent-sessions-clarification-input"
              disabled={clarifying}
            />
            <Button
              type="submit"
              loading={clarifying}
              disabled={!clarificationAnswer.trim()}
              data-testid="agent-sessions-clarification-submit"
            >
              {clarifying ? t('agentSessions.clarificationSubmitting') : t('agentSessions.clarificationSubmit')}
            </Button>
            {clarifyError ? (
              <p className="text-sm text-[var(--color-danger)]">{clarifyError}</p>
            ) : null}
          </form>
        </AgentSection>
      ) : null}

      {session.status === 'failed' && session.error ? (
        <p className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-[var(--color-danger)]">
          {session.error}
        </p>
      ) : null}

      {studentSummary?.headline && policyAnswer ? (
        <AgentSection title={t('agentSessions.summaryTitle')} testId="agent-sessions-summary" accent="primary">
          <p className="font-medium">{studentSummary.headline}</p>
          {studentSummary.rationale ? (
            <p className="mt-2 text-[var(--color-text-muted)]">{studentSummary.rationale}</p>
          ) : null}
          {(studentSummary.trade_offs?.length ?? 0) > 0 ? (
            <ul className="mt-2 list-disc ps-4 text-[var(--color-text-muted)]">
              {studentSummary.trade_offs?.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </AgentSection>
      ) : null}

      {(studentSummary?.trade_offs?.length ?? 0) > 0 && !policyAnswer && studentSummary?.headline ? (
        <AgentSection title={t('agentSessions.summaryTitle')} testId="agent-sessions-trade-offs">
          <ul className="list-disc ps-4 text-[var(--color-text-muted)]">
            {studentSummary.trade_offs?.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </AgentSection>
      ) : null}

      {courses.length > 0 ? (
        <div id="agent-session-schedule" className="scroll-mt-24">
        <AgentScheduleBoard
          courses={courses}
          title={t('agentSessions.scheduleTitle')}
          noSlotsLabel={t('agentSessions.noScheduleSlots')}
          gridViewLabel={t('agentSessions.scheduleGridView')}
          listViewLabel={t('agentSessions.scheduleListView')}
        />
        </div>
      ) : null}

      {utilityComponents ? (
        <div id="agent-session-score" className="scroll-mt-24">
        <AgentUtilityBreakdown
          title={t('agentSessions.utilityBreakdownTitle')}
          components={utilityComponents}
          labels={{
            progress_gain: t('agentSessions.utilityProgressGain'),
            path_alignment: t('agentSessions.utilityPathAlignment'),
            prereq_safety: t('agentSessions.utilityPrereqSafety'),
            load_balance: t('agentSessions.utilityLoadBalance'),
            preference_match: t('agentSessions.utilityPreferenceMatch'),
            risk_penalty: t('agentSessions.utilityRiskPenalty'),
          }}
        />
        </div>
      ) : null}

      {utility && !courseIds.length ? (
        <AgentSection title={t('agentSessions.utilityTitle')}>
          <p className="text-[var(--color-text-muted)]">
            {t('agentSessions.utilityScore', { score: String(utility.utility ?? '—') })}
          </p>
        </AgentSection>
      ) : null}

      {softCritiques.length > 0 ? (
        <AgentSection title={t('agentSessions.softCritiquesTitle')}>
          <ul className="space-y-2 text-[var(--color-text-muted)]">
            {softCritiques.map((critique, index) => (
              <li
                key={`${critique.type}-${index}`}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2"
              >
                {String(critique.message ?? critique.type ?? t('agentSessions.preferenceNote'))}
              </li>
            ))}
          </ul>
        </AgentSection>
      ) : null}

      {hasAdvancedAnalysis ? (
        <div id="agent-session-advanced" className="scroll-mt-24">
        <AgentCollapsibleSection
          title={t('agentSessions.advancedAnalysisTitle')}
          description={t('agentSessions.advancedAnalysisHint')}
          testId="agent-sessions-advanced"
        >
          <div className="space-y-4">
            {counterfactuals.length > 0 ? (
              <div data-testid="agent-sessions-counterfactuals">
                <p className="mb-2 text-sm font-semibold">{t('agentSessions.counterfactualTitle')}</p>
                <ul className="space-y-2 text-[var(--color-text-muted)]">
                  {counterfactuals.map((entry, index) => (
                    <li
                      key={`${String(entry.variant)}-${index}`}
                      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2"
                    >
                      <span className="font-medium text-[var(--color-text)]">
                        {t('agentSessions.counterfactualVariant', { variant: String(entry.variant ?? '—') })}
                      </span>
                      <p className="mt-1">{String(entry.reason ?? '')}</p>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {redTeamReview && (redTeamReview.attackCount ?? 0) > 0 ? (
              <div data-testid="agent-sessions-red-team">
                <p className="mb-2 text-sm font-semibold">{t('agentSessions.redTeamTitle')}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('agentSessions.redTeamSeverity', { severity: String(redTeamReview.severity ?? 'unknown') })}
                </p>
                <ul className="mt-3 space-y-2 text-[var(--color-text-muted)]">
                  {(redTeamReview.attacks ?? []).map((attack, index) => (
                    <li
                      key={`${attack.type}-${index}`}
                      className="rounded-lg border border-[var(--color-border)] bg-white px-3 py-2"
                    >
                      {String(attack.message ?? attack.type ?? '')}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {replayEvents.length > 0 ? (
              <div data-testid="agent-sessions-replay">
                <p className="mb-2 text-sm font-semibold">{t('agentSessions.replayTitle')}</p>
                <ol className="space-y-2 text-[var(--color-text-muted)]">
                  {replayEvents.map((event, index) => (
                    <li
                      key={`${String(event.event)}-${index}`}
                      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2"
                    >
                      <span className="font-medium capitalize text-[var(--color-text)]">
                        {String(event.event ?? 'step').replace(/_/g, ' ')}
                      </span>
                      {typeof event.round === 'number' ? (
                        <span className="ms-2 text-xs">round {event.round}</span>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        </AgentCollapsibleSection>
        </div>
      ) : null}

      {session.status === 'completed' && courseIds.length > 0 ? (
        <AgentActionBar
          isApproved={isApproved}
          isApplied={isApplied}
          appliedPlanId={session.appliedPlanId}
          approving={approving}
          applying={applying}
          onApprove={onApprove}
          onApply={onApply}
          approveLabel={t('agentSessions.approve')}
          approvedLabel={t('agentSessions.approved')}
          applyLabel={t('agentSessions.applyPlan')}
          appliedLabel={t('agentSessions.appliedPlan')}
          openPlannerLabel={t('agentSessions.openPlanner')}
          approvalRequiredLabel={t('agentSessions.approvalRequired')}
        />
      ) : null}

      {session.status === 'completed' && onSecondOpinion ? (
        <AgentSection
          title={t('agentSessions.secondOpinionTitle')}
          testId="agent-sessions-second-opinion"
          description={t('agentSessions.secondOpinionHint')}
        >
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="secondary"
              loading={secondOpinionLoading}
              disabled={secondOpinionLoading}
              onClick={() => onSecondOpinion('risk_averse')}
              data-testid="agent-sessions-second-opinion-risk"
            >
              {t('agentSessions.secondOpinionRiskAverse')}
            </Button>
            <Button
              type="button"
              variant="secondary"
              loading={secondOpinionLoading}
              disabled={secondOpinionLoading}
              onClick={() => onSecondOpinion('aggressive')}
              data-testid="agent-sessions-second-opinion-aggressive"
            >
              {t('agentSessions.secondOpinionAggressive')}
            </Button>
          </div>
          {secondOpinionError ? (
            <p className="mt-2 text-sm text-[var(--color-danger)]">{secondOpinionError}</p>
          ) : null}
        </AgentSection>
      ) : null}

      {session.transcript.length > 0 ? (
        <div id="agent-session-transcript" className="scroll-mt-24">
        <AgentTranscriptTimeline
          turns={session.transcript}
          title={t('agentSessions.transcriptTitle')}
          actionLabel={actionLabel}
          renderReasoning={(turn) => <TranscriptReasoning turn={turn} t={t} />}
        />
        </div>
      ) : null}

      {applyError ? <p className="text-sm text-[var(--color-danger)]">{applyError}</p> : null}

      {session.transcript.length > 0 && session.status === 'completed' ? (
        <div id="agent-session-why" className="scroll-mt-24">
        <AgentSection title={t('agentSessions.whyTitle')} testId="agent-sessions-why" description={t('agentSessions.whyHint')}>
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={(event) => {
              event.preventDefault()
              const trimmed = whyQuestion.trim()
              if (!trimmed || askingWhy || !onAskWhy) return
              onAskWhy(trimmed)
            }}
          >
            <input
              className="flex-1 rounded-xl border border-[var(--color-border)] bg-white px-3 py-2 text-sm outline-none transition focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20"
              value={whyQuestion}
              onChange={(event) => setWhyQuestion(event.target.value)}
              placeholder={t('agentSessions.whyPlaceholder')}
              disabled={askingWhy}
              data-testid="agent-sessions-why-input"
            />
            <Button
              type="submit"
              variant="secondary"
              loading={askingWhy}
              disabled={askingWhy || !whyQuestion.trim()}
              data-testid="agent-sessions-why-submit"
            >
              {askingWhy ? t('agentSessions.whySubmitting') : t('agentSessions.whySubmit')}
            </Button>
          </form>
          {whyError ? <p className="mt-2 text-sm text-[var(--color-danger)]">{whyError}</p> : null}
          {whyAnswer ? (
            <div className="mt-4 space-y-3" data-testid="agent-sessions-why-answer">
              <p className="whitespace-pre-wrap text-[var(--color-text-muted)]">{whyAnswer.answer}</p>
              {whyAnswer.citations.length > 0 ? (
                <ul className="space-y-2 text-xs text-[var(--color-text-muted)]">
                  {whyAnswer.citations.map((citation, index) => (
                    <li
                      key={`${String(citation.agentRole)}-${index}`}
                      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 px-3 py-2"
                    >
                      <span className="font-medium text-[var(--color-text)]">
                        {formatAgentRole(String(citation.agentRole ?? 'agent'))}
                      </span>
                      {citation.excerpt ? <p className="mt-1">{String(citation.excerpt)}</p> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ) : null}
        </AgentSection>
        </div>
      ) : null}
    </div>
  )
}

export function AgentSessionsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [goal, setGoal] = useState('')
  const [avoidFriday, setAvoidFriday] = useState(false)
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [applyError, setApplyError] = useState<string | null>(null)
  const [clarifyError, setClarifyError] = useState<string | null>(null)
  const [whyError, setWhyError] = useState<string | null>(null)
  const [secondOpinionError, setSecondOpinionError] = useState<string | null>(null)
  const [whyAnswer, setWhyAnswer] = useState<{
    answer: string
    citations: Array<Record<string, unknown>>
    topics: string[]
  } | null>(null)
  const [liveStreamEvents, setLiveStreamEvents] = useState<Array<Record<string, unknown>>>([])
  const [streamConnected, setStreamConnected] = useState(false)

  const suggestedGoals = useMemo(
    () => [
      t('agentSessions.promptPlan'),
      t('agentSessions.promptGraduation'),
      t('agentSessions.promptCourse'),
      t('agentSessions.promptLightLoad'),
    ],
    [t],
  )

  const agentRoleLabel = useCallback(
    (role: string) => {
      const key = `agentSessions.role_${role}` as const
      const translated = t(key)
      return translated === key ? formatAgentRole(role) : translated
    },
    [t],
  )

  const historyQuery = useQuery({
    queryKey: ['agent-sessions'],
    queryFn: () => agentSessionsApi.list(),
  })

  const sessionQuery = useQuery({
    queryKey: ['agent-session', activeSessionId],
    queryFn: () => agentSessionsApi.get(activeSessionId as string),
    enabled: Boolean(activeSessionId),
    refetchInterval: (query) => {
      if (streamConnected) return false
      const status = query.state.data?.session.status
      return status && ACTIVE_STATUSES.has(status) ? 2000 : false
    },
  })

  const replayQuery = useQuery({
    queryKey: ['agent-session-replay', activeSessionId],
    queryFn: () => agentSessionsApi.replay(activeSessionId as string),
    enabled: Boolean(
      activeSessionId &&
        sessionQuery.data?.session &&
        !ACTIVE_STATUSES.has(sessionQuery.data.session.status),
    ),
  })

  const createMutation = useMutation({
    mutationFn: (nextGoal: string) =>
      agentSessionsApi.create({
        goal: nextGoal,
        constraints: avoidFriday ? { avoidDays: ['שישי'] } : {},
      }),
    onSuccess: (data) => {
      setApplyError(null)
      setActiveSessionId(data.session.id)
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
    },
  })

  const approveMutation = useMutation({
    mutationFn: (sessionId: string) => agentSessionsApi.approve(sessionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['agent-session', activeSessionId] })
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
    },
  })

  const clarifyMutation = useMutation({
    mutationFn: ({ sessionId, clarification }: { sessionId: string; clarification: string }) =>
      agentSessionsApi.clarify(sessionId, clarification),
    onSuccess: () => {
      setClarifyError(null)
      void queryClient.invalidateQueries({ queryKey: ['agent-session', activeSessionId] })
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
    },
    onError: (error: Error) => {
      setClarifyError(error.message || t('agentSessions.applyError'))
    },
  })

  const whyMutation = useMutation({
    mutationFn: ({ sessionId, question }: { sessionId: string; question: string }) =>
      agentSessionsApi.why(sessionId, question),
    onSuccess: (data) => {
      setWhyError(null)
      setWhyAnswer({
        answer: data.answer,
        citations: data.citations,
        topics: data.topics,
      })
    },
    onError: (error: Error) => {
      setWhyError(error.message || t('agentSessions.applyError'))
    },
  })

  const secondOpinionMutation = useMutation({
    mutationFn: ({
      sessionId,
      utilityProfile,
    }: {
      sessionId: string
      utilityProfile: 'balanced' | 'risk_averse' | 'aggressive'
    }) => agentSessionsApi.secondOpinion(sessionId, utilityProfile),
    onSuccess: (data) => {
      setSecondOpinionError(null)
      setActiveSessionId(data.session.id)
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
    },
    onError: (error: Error) => {
      setSecondOpinionError(error.message || t('agentSessions.applyError'))
    },
  })

  const applyMutation = useMutation({
    mutationFn: (sessionId: string) => agentSessionsApi.apply(sessionId),
    onSuccess: (data) => {
      setApplyError(null)
      void queryClient.invalidateQueries({ queryKey: ['agent-session', activeSessionId] })
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
      void queryClient.invalidateQueries({ queryKey: ['semester-plans'] })
      if (data.semesterPlanId) {
        navigate(`/plans/${data.semesterPlanId}/edit`)
      }
    },
    onError: (error: Error) => {
      setApplyError(error.message || t('agentSessions.applyError'))
    },
  })

  useEffect(() => {
    setWhyAnswer(null)
    setWhyError(null)
    setSecondOpinionError(null)
    setLiveStreamEvents([])
    setStreamConnected(false)
  }, [activeSessionId])

  useEffect(() => {
    if (!activeSessionId) return undefined
    const status = sessionQuery.data?.session.status
    if (!status || !ACTIVE_STATUSES.has(status)) {
      return undefined
    }

    const source = new EventSource(`${getApiBaseUrl()}/agent/sessions/${activeSessionId}/stream`, {
      withCredentials: true,
    })
    setStreamConnected(true)

    const onPhase = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as Record<string, unknown>
        setLiveStreamEvents((previous) => [...previous, data])
        void queryClient.invalidateQueries({ queryKey: ['agent-session', activeSessionId] })
      } catch {
        // Ignore malformed stream payloads.
      }
    }

    const onDone = () => {
      void queryClient.invalidateQueries({ queryKey: ['agent-session', activeSessionId] })
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
      void queryClient.invalidateQueries({ queryKey: ['agent-session-replay', activeSessionId] })
      source.close()
      setStreamConnected(false)
    }

    const onSessionCompleted = (event: MessageEvent<string>) => {
      try {
        const data = JSON.parse(event.data) as Record<string, unknown>
        setLiveStreamEvents((previous) => [...previous, data])
      } catch {
        // Ignore malformed stream payloads.
      }
      onDone()
    }

    source.addEventListener('phase', onPhase)
    source.addEventListener('session_completed', onSessionCompleted)
    source.addEventListener('done', onDone)
    source.onerror = () => {
      source.close()
      setStreamConnected(false)
    }

    return () => {
      source.removeEventListener('phase', onPhase)
      source.removeEventListener('session_completed', onSessionCompleted)
      source.removeEventListener('done', onDone)
      source.close()
      setStreamConnected(false)
    }
  }, [activeSessionId, queryClient, sessionQuery.data?.session.status])

  useEffect(() => {
    if (
      sessionQuery.data?.session.status === 'completed' ||
      sessionQuery.data?.session.status === 'failed' ||
      sessionQuery.data?.session.status === 'awaiting_clarification'
    ) {
      void queryClient.invalidateQueries({ queryKey: ['agent-sessions'] })
    }
  }, [queryClient, sessionQuery.data?.session.status])

  const submitGoal = (nextGoal: string) => {
    const trimmed = nextGoal.trim()
    if (!trimmed || createMutation.isPending) return
    setGoal('')
    createMutation.mutate(trimmed)
  }

  const activeSession = sessionQuery.data?.session

  const statusLabel = useCallback(
    (status: string) => {
      const labels: Record<string, string> = {
        pending: t('agentSessions.statusPending'),
        processing: t('agentSessions.statusProcessing'),
        completed: t('agentSessions.statusCompleted'),
        failed: t('agentSessions.statusFailed'),
        awaiting_clarification: t('agentSessions.statusAwaitingClarification'),
      }
      return labels[status] ?? status
    },
    [t],
  )

  const workflowSteps = useMemo(
    () => [
      { id: 'compose' as const, label: t('agentSessions.workflowCompose') },
      { id: 'negotiate' as const, label: t('agentSessions.workflowNegotiate') },
      { id: 'review' as const, label: t('agentSessions.workflowReview') },
      { id: 'apply' as const, label: t('agentSessions.workflowApply') },
    ],
    [t],
  )

  const activeWorkflowStep = resolveWorkflowStep(activeSession)

  return (
    <div className="animate-fade-in space-y-6" data-testid="agent-sessions-page">
      <PageHeader title={t('agentSessions.title')} description={t('agentSessions.subtitle')} />

      <AgentWorkflowStepper steps={workflowSteps} activeStep={activeWorkflowStep} />

      <div className="grid gap-6 lg:grid-cols-12 lg:items-start">
        <aside className="order-2 space-y-6 lg:order-1 lg:col-span-4 xl:col-span-4">
          <AgentComposePanel
            suggestedGoals={suggestedGoals}
            goal={goal}
            onGoalChange={setGoal}
            onSubmitGoal={submitGoal}
            avoidFriday={avoidFriday}
            onAvoidFridayChange={setAvoidFriday}
            isSubmitting={createMutation.isPending}
            errorMessage={createMutation.isError ? (createMutation.error as Error).message : null}
            title={t('agentSessions.multiAgentTitle')}
            hint={t('agentSessions.multiAgentHint')}
            goalLabel={t('agentSessions.goalLabel')}
            goalPlaceholder={t('agentSessions.goalPlaceholder')}
            startLabel={t('agentSessions.start')}
            avoidFridayLabel={t('agentSessions.avoidFriday')}
            suggestionLabel={t('agentSessions.suggestionPromptsLabel')}
            rosterLabel={t('agentSessions.rosterLabel')}
            roleLabel={agentRoleLabel}
          />

          <AgentHistoryPanel
            sessions={historyQuery.data?.sessions ?? []}
            activeSessionId={activeSessionId}
            onSelect={setActiveSessionId}
            title={t('agentSessions.historyTitle')}
            statusLabel={statusLabel}
          />
        </aside>

        <main className="order-1 min-w-0 space-y-6 lg:order-2 lg:col-span-8 xl:col-span-8">
          {activeSession ? (
            <Card className="space-y-5 p-4 sm:p-6" data-testid="agent-sessions-active-panel">
              <AgentActiveSessionHeader
                goal={activeSession.goal}
                statusLabel={statusLabel(activeSession.status)}
                statusToneValue={statusTone(activeSession.status)}
                activeSessionTitle={t('agentSessions.activeSessionTitle')}
                updatedAt={activeSession.updatedAt}
                rounds={activeSession.rounds}
                updatedLabel={t('agentSessions.sessionUpdatedLabel')}
                roundsLabel={t('agentSessions.sessionRoundsLabel')}
              />

              {ACTIVE_STATUSES.has(activeSession.status) ? (
                <AgentLivePanel
                  negotiatingLabel={t('agentSessions.negotiating')}
                  streamTitle={t('agentSessions.streamTitle')}
                  events={liveStreamEvents}
                  connected={streamConnected}
                  connectedLabel={t('agentSessions.liveConnectedLabel')}
                  connectingLabel={t('agentSessions.liveConnectingLabel')}
                  roleLabel={agentRoleLabel}
                  eventLabel={(event) => {
                    const eventName = String(event.event ?? event.phase ?? 'step').replace(/_/g, ' ')
                    return eventName.charAt(0).toUpperCase() + eventName.slice(1)
                  }}
                />
              ) : (
                <SessionResult
                  session={activeSession}
                  replayEvents={replayQuery.data?.events ?? []}
                  whyAnswer={whyAnswer}
                  approving={approveMutation.isPending}
                  applying={applyMutation.isPending}
                  clarifying={clarifyMutation.isPending}
                  askingWhy={whyMutation.isPending}
                  secondOpinionLoading={secondOpinionMutation.isPending}
                  applyError={applyError}
                  clarifyError={clarifyError}
                  whyError={whyError}
                  secondOpinionError={secondOpinionError}
                  onApprove={() => {
                    if (!activeSession.id) return
                    approveMutation.mutate(activeSession.id)
                  }}
                  onApply={() => {
                    if (!activeSession.id) return
                    setApplyError(null)
                    applyMutation.mutate(activeSession.id)
                  }}
                  onClarify={(clarification) => {
                    if (!activeSession.id) return
                    setClarifyError(null)
                    clarifyMutation.mutate({ sessionId: activeSession.id, clarification })
                  }}
                  onAskWhy={(question) => {
                    if (!activeSession.id) return
                    setWhyError(null)
                    whyMutation.mutate({ sessionId: activeSession.id, question })
                  }}
                  onSecondOpinion={(utilityProfile) => {
                    if (!activeSession.id) return
                    setSecondOpinionError(null)
                    secondOpinionMutation.mutate({ sessionId: activeSession.id, utilityProfile })
                  }}
                />
              )}
            </Card>
          ) : (
            <div data-testid="agent-sessions-empty">
              <EmptyState
                title={t('agentSessions.emptySessionTitle')}
                description={t('agentSessions.emptySessionHint')}
              />
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
