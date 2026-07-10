import { useParams, Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Pencil } from 'lucide-react'
import { plansApi } from '../api/endpoints'
import { OpenInWhatIfLink } from '../components/simulations/OpenInWhatIfLink'
import { ExamSummaryPanel } from '../components/plans/ExamSummaryPanel'
import { SharePlanPanel } from '../components/plans/SharePlanPanel'
import { WeeklyScheduleGrid } from '../components/plans/WeeklyScheduleGrid'
import { Button } from '../components/ui/Button'
import { Badge, Card, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { buildPlanWhatIfText } from '../lib/simulationLinks'
import { invalidateRecommendations } from '../lib/recommendationsQuery'
import { formatCredits } from '../lib/utils'

export function PlanDetailPage() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const planQuery = useQuery({
    queryKey: ['plan', id],
    queryFn: () => plansApi.get(id),
    enabled: Boolean(id),
  })

  const forkMutation = useMutation({
    mutationFn: () => plansApi.forkVersion(id),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
      void invalidateRecommendations(queryClient)
      navigate(`/plans/${data.semesterPlan.id}/edit`)
    },
  })

  if (planQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  const plan = planQuery.data?.semesterPlan
  if (!plan) return null

  const isManual = plan.plannerType === 'manual'

  return (
    <div className="animate-fade-in space-y-6">
      <Link
        to="/plans"
        className="inline-flex items-center gap-2 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
      >
        <ArrowLeft className="h-4 w-4" />
        {t('common.back')}
      </Link>

      <PageHeader
        title={plan.name ?? `Semester plan v${plan.version}`}
        description={plan.explanation?.summary}
        action={
          <div className="flex flex-wrap gap-2">
            <OpenInWhatIfLink
              text={buildPlanWhatIfText(plan)}
              planId={plan.id}
              variant="button"
              testId="plan-what-if"
            />
            {isManual && plan.status !== 'archived' ? (
              <Link to={`/plans/${plan.id}/edit`}>
                <Button variant="secondary">
                  <Pencil className="h-4 w-4" />
                  {t('common.edit')}
                </Button>
              </Link>
            ) : null}
            {plan.status !== 'archived' ? (
              <Button variant="ghost" loading={forkMutation.isPending} onClick={() => forkMutation.mutate()}>
                {t('plans.createVersion')}
              </Button>
            ) : null}
          </div>
        }
      />

      <div className="flex flex-wrap gap-2">
        <Badge tone="primary">
          {isManual ? t('plans.plannerManual') : t('plans.plannerAuto')}
        </Badge>
        <Badge tone="neutral">v{plan.version}</Badge>
        <Badge tone={plan.status === 'draft' ? 'warning' : 'success'}>
          {plan.status === 'draft'
            ? t('plans.statusDraft')
            : plan.status === 'archived'
              ? t('plans.statusArchived')
              : t('plans.statusActive')}
        </Badge>
      </div>

      {plan.plannerInsights?.creditsWarning ? (
        <Card className="border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5">
          <p className="text-sm text-[var(--color-warning)]">{plan.plannerInsights.creditsWarning.message}</p>
        </Card>
      ) : null}

      <SharePlanPanel planId={plan.id} plan={plan} />

      {plan.semesters.map((semester) => (
        <Card key={semester.semesterCode}>
          <h2 className="mb-4 text-sm font-semibold">
            {semester.semesterCode}
            {semester.goalCredits
              ? ` · ${formatCredits(semester.goalCredits)} ${t('common.credits')}`
              : ''}
          </h2>
          <div className="space-y-3">
            {semester.plannedCourses.map((course) => (
              <div
                key={`${course.courseId}-${course.courseNumber}`}
                className="flex flex-col gap-1 rounded-xl bg-[var(--color-surface-muted)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="font-mono text-sm text-[var(--color-primary)]">{course.courseNumber}</p>
                  <p className="text-sm">{course.courseTitle ?? 'Course'}</p>
                  {course.reason ? (
                    <p className="text-xs text-[var(--color-text-muted)]">{course.reason}</p>
                  ) : null}
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <Badge tone="neutral">{course.category ?? 'course'}</Badge>
                  <span>
                    {formatCredits(course.credits)} {t('common.credits')}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-6 border-t border-[var(--color-border)] pt-6">
            <h3 className="mb-3 text-sm font-semibold">{t('plans.weeklySchedule')}</h3>
            <WeeklyScheduleGrid schedule={semester.weeklySchedule} />
          </div>
        </Card>
      ))}

      <ExamSummaryPanel summary={plan.plannerInsights?.examSummary} />
    </div>
  )
}
