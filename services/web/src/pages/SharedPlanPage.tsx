import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { plansApi } from '../api/endpoints'
import { ExamSummaryPanel } from '../components/plans/ExamSummaryPanel'
import { PlannerSummaryBar } from '../components/plans/PlannerSummaryBar'
import { WeeklyScheduleGrid } from '../components/plans/WeeklyScheduleGrid'
import { Badge, Card, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { formatCredits } from '../lib/utils'

export function SharedPlanPage() {
  const { token = '' } = useParams()
  const { t } = useTranslation()

  const planQuery = useQuery({
    queryKey: ['shared-plan', token],
    queryFn: () => plansApi.getShared(token),
    enabled: Boolean(token),
  })

  if (planQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-surface)]">
        <Spinner />
      </div>
    )
  }

  const plan = planQuery.data?.semesterPlan
  if (planQuery.isError || !plan) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-surface)] px-4">
        <Card className="max-w-md text-center">
          <p className="text-sm text-[var(--color-danger)]">{t('planner.sharedNotFound')}</p>
        </Card>
      </div>
    )
  }

  const semester = plan.semesters[0]
  const activeCourses = (semester?.plannedCourses ?? []).filter((course) => course.isActive !== false)
  const totalCredits = activeCourses.reduce((sum, course) => sum + (course.credits ?? 0), 0)
  const insights = plan.plannerInsights

  return (
    <div className="min-h-screen bg-[var(--color-surface)] px-4 py-8">
      <div className="mx-auto max-w-5xl space-y-6 animate-fade-in">
        <PageHeader
          title={plan.name ?? t('plans.title')}
          description={t('planner.sharedReadOnlyHint')}
        />

        <div className="flex flex-wrap gap-2">
          <Badge tone="neutral">{t('planner.readOnly')}</Badge>
          <Badge tone="primary">{semester?.semesterCode}</Badge>
        </div>

        <PlannerSummaryBar
          activeCount={activeCourses.length}
          totalCount={semester?.plannedCourses.length ?? 0}
          activeCredits={totalCredits}
          conflictCount={insights?.scheduleConflicts?.length ?? 0}
          examCount={insights?.examSummary?.totalExams ?? insights?.examSummary?.exams?.length ?? 0}
          maxCredits={insights?.maxCreditsPerSemester}
        />

        <Card>
          <h2 className="mb-4 text-sm font-semibold">{t('plans.selectedCourses')}</h2>
          <div className="space-y-2">
            {(semester?.plannedCourses ?? []).map((course) => (
              <div
                key={course.courseId}
                className={`rounded-xl border px-4 py-3 ${
                  course.isActive === false ? 'opacity-60' : ''
                } border-[var(--color-border)] bg-[var(--color-surface-muted)]`}
              >
                <p className="font-mono text-xs text-[var(--color-primary)]">{course.courseNumber}</p>
                <p className="text-sm font-medium">{course.courseTitle}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {formatCredits(course.credits ?? 0)} {t('common.credits')}
                  {course.isActive === false ? ` · ${t('planner.inactive')}` : ''}
                </p>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h3 className="mb-4 text-sm font-semibold">{t('plans.weeklySchedule')}</h3>
          <WeeklyScheduleGrid
            schedule={semester?.weeklySchedule}
            customEvents={semester?.customEvents ?? semester?.weeklySchedule?.customEvents}
          />
        </Card>

        <ExamSummaryPanel summary={insights?.examSummary} />
      </div>
    </div>
  )
}
