import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Eye } from 'lucide-react'
import { plansApi } from '../api/endpoints'
import { ExamSummaryPanel } from '../components/plans/ExamSummaryPanel'
import { PlannerSummaryBar } from '../components/plans/PlannerSummaryBar'
import { WeeklyScheduleGrid } from '../components/plans/WeeklyScheduleGrid'
import { Badge, Card, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { courseColorStyles } from '../lib/plannerColors'
import { buildPlanChanges } from '../lib/plannerChanges'
import { semesterLabel } from '../lib/semester'
import { formatCredits } from '../lib/utils'

export function SharedPlanPage() {
  const { token = '' } = useParams()
  const { t, locale } = useTranslation()

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
  const changes = buildPlanChanges(insights)
  const missingLessonCount = insights?.lessonSelectionWarnings?.filter(
    (warning) => warning.type === 'missing_selection',
  ).length ?? 0

  return (
    <div className="min-h-screen bg-[var(--color-surface-muted)] px-4 py-8 print:bg-white print:px-0">
      <div className="mx-auto max-w-6xl space-y-6 animate-fade-in">
        <div className="rounded-xl border border-[var(--color-warning)] bg-[var(--color-warning)]/10 px-4 py-3 print:hidden">
          <p className="flex items-center gap-2 text-sm font-medium text-[var(--color-warning)]">
            <Eye className="h-4 w-4 shrink-0" />
            {t('planner.sharedReadOnlyBanner')}
          </p>
        </div>

        <PageHeader
          title={plan.name ?? t('plans.title')}
          description={t('planner.sharedReadOnlyHint')}
        />

        <div className="flex flex-wrap gap-2 print:hidden">
          <Badge tone="neutral">{t('planner.readOnly')}</Badge>
          {semester?.semesterCode ? (
            <Badge tone="primary">{semesterLabel(semester.semesterCode, locale)}</Badge>
          ) : null}
        </div>

        <p className="hidden text-sm text-[var(--color-text-muted)] print:block">
          {semester?.semesterCode ? semesterLabel(semester.semesterCode, locale) : ''}
        </p>

        <PlannerSummaryBar
          activeCount={activeCourses.length}
          totalCount={semester?.plannedCourses.length ?? 0}
          activeCredits={totalCredits}
          conflictCount={insights?.scheduleConflicts?.length ?? 0}
          examCount={insights?.examSummary?.totalExams ?? insights?.examSummary?.exams?.length ?? 0}
          maxCredits={insights?.maxCreditsPerSemester}
          missingLessonCount={missingLessonCount}
          changesCount={changes.length}
        />

        <div className="grid gap-6 lg:grid-cols-[minmax(280px,340px)_1fr]">
          <div className="space-y-4 print:hidden">
            <Card>
              <h2 className="mb-4 text-sm font-semibold">{t('plans.selectedCourses')}</h2>
              <div className="space-y-2">
                {(semester?.plannedCourses ?? []).map((course) => {
                  const courseNumber = course.courseNumber ?? course.courseId ?? ''
                  const colorStyles = courseColorStyles(courseNumber)
                  return (
                    <div
                      key={course.courseId}
                      className={`rounded-xl border px-4 py-3 ${
                        course.isActive === false ? 'opacity-60' : ''
                      }`}
                      style={{
                        borderColor: colorStyles.borderColor,
                        backgroundColor: colorStyles.backgroundColor,
                      }}
                    >
                      <p className="font-mono text-xs" style={{ color: colorStyles.color }}>
                        {course.courseNumber}
                      </p>
                      <p className="text-sm font-medium">{course.courseTitle}</p>
                      <p className="text-xs text-[var(--color-text-muted)]">
                        {formatCredits(course.credits ?? 0)} {t('common.credits')}
                        {course.isActive === false ? ` · ${t('planner.inactive')}` : ''}
                      </p>
                    </div>
                  )
                })}
              </div>
            </Card>

            <ExamSummaryPanel summary={insights?.examSummary} />
          </div>

          <Card className="print:border-0 print:shadow-none">
            <h3 className="mb-4 text-sm font-semibold">{t('plans.weeklySchedule')}</h3>
            <WeeklyScheduleGrid schedule={semester?.weeklySchedule} />
          </Card>
        </div>
      </div>
    </div>
  )
}
