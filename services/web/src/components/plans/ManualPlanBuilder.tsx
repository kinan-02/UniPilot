import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowRight, BookPlus, CalendarPlus, ChevronLeft, Trash2, Wand2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { plansApi, profileApi } from '../../api/endpoints'
import { isAuthError } from '../../auth/AuthContext'
import { CourseSearchCombobox } from '../catalog/CourseSearchCombobox'
import { PlanBuilderStepper, type BuilderStep } from './PlanBuilderStepper'
import { PlanBuilderSummary } from './PlanBuilderSummary'
import { SemesterPicker } from './SemesterPicker'
import { WeeklyScheduleView } from './WeeklyScheduleView'
import { Button } from '../ui/Button'
import { Card, Spinner } from '../ui/Card'
import { Input } from '../ui/Input'
import { useTranslation } from '../../i18n'
import { ensurePlanningProfile, courseTitle } from '../../lib/planning'
import {
  defaultSemesterCode,
  parseSemesterCode,
  suggestedPlanName,
} from '../../lib/semester'
import {
  validateCredits,
  validatePlanName,
  validateSemesterCode,
} from '../../lib/validation'
import type { CourseSummary, PlannedCourse, SemesterPlan } from '../../types/api'
import { formatCredits } from '../../lib/utils'

export type DraftCourse = {
  courseId: string
  courseNumber: string
  courseTitle: string
  credits: number
}

type ManualPlanBuilderProps = {
  planId?: string
}

function mapPlanToDraft(plan: SemesterPlan) {
  const semester = plan.semesters[0]
  return {
    name: plan.name ?? '',
    semesterCode: semester?.semesterCode ?? defaultSemesterCode(),
    goalCredits: String(semester?.goalCredits ?? ''),
    courses: (semester?.plannedCourses ?? []).map((course) => ({
      courseId: course.courseId,
      courseNumber: course.courseNumber ?? '',
      courseTitle: course.courseTitle ?? '',
      credits: course.credits ?? 0,
    })),
    scheduleEnabled: Boolean(semester?.weeklySchedule?.entries?.length),
    previewSchedule: semester?.weeklySchedule,
  }
}

export function ManualPlanBuilder({ planId }: ManualPlanBuilderProps) {
  const { t, locale } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isEdit = Boolean(planId)

  const planQuery = useQuery({
    queryKey: ['plan', planId],
    queryFn: () => plansApi.get(planId!),
    enabled: isEdit,
  })

  const [step, setStep] = useState<BuilderStep>('basics')
  const [name, setName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [semesterCode, setSemesterCode] = useState(defaultSemesterCode())
  const [goalCredits, setGoalCredits] = useState('12')
  const [courses, setCourses] = useState<DraftCourse[]>([])
  const [scheduleEnabled, setScheduleEnabled] = useState(false)
  const [previewSchedule, setPreviewSchedule] = useState(
    planQuery.data?.semesterPlan.semesters[0]?.weeklySchedule,
  )
  const [errors, setErrors] = useState<string[]>([])
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!planQuery.data?.semesterPlan) return
    const draft = mapPlanToDraft(planQuery.data.semesterPlan)
    setName(draft.name)
    setNameTouched(true)
    setSemesterCode(draft.semesterCode)
    setGoalCredits(draft.goalCredits || '12')
    setCourses(draft.courses)
    setScheduleEnabled(draft.scheduleEnabled)
    setPreviewSchedule(draft.previewSchedule)
    if (draft.courses.length) setStep('schedule')
  }, [planQuery.data])

  useEffect(() => {
    if (nameTouched) return
    setName(suggestedPlanName(semesterCode, locale))
  }, [semesterCode, locale, nameTouched])

  const totalCredits = useMemo(
    () => courses.reduce((sum, course) => sum + (course.credits || 0), 0),
    [courses],
  )

  const parsedSemester = parseSemesterCode(semesterCode)
  const goalNumber = goalCredits ? Number(goalCredits) : null

  const stepLabels: Record<BuilderStep, string> = {
    basics: t('plans.stepBasics'),
    courses: t('plans.stepCourses'),
    schedule: t('plans.stepSchedule'),
  }

  const addCourse = (course: CourseSummary) => {
    if (!course.id) return
    if (courses.some((item) => item.courseId === course.id)) {
      setErrors([t('validation.duplicateCourse')])
      return
    }
    setErrors([])
    setCourses((prev) => [
      ...prev,
      {
        courseId: course.id!,
        courseNumber: course.courseNumber,
        courseTitle: courseTitle(course, locale),
        credits: course.credits ?? 0,
      },
    ])
  }

  const removeCourse = (courseId: string) => {
    setCourses((prev) => prev.filter((course) => course.courseId !== courseId))
  }

  const validateBasics = (): boolean => {
    const nextFieldErrors: Record<string, string> = {}
    const nameResult = validatePlanName(name)
    if (!nameResult.ok) nextFieldErrors.name = t(nameResult.message)

    const semesterResult = validateSemesterCode(semesterCode)
    if (!semesterResult.ok) nextFieldErrors.semesterCode = t(semesterResult.message)

    if (goalCredits) {
      const creditsResult = validateCredits(Number(goalCredits))
      if (!creditsResult.ok) nextFieldErrors.goalCredits = t(creditsResult.message)
    }

    setFieldErrors(nextFieldErrors)
    return Object.keys(nextFieldErrors).length === 0
  }

  const validateCourses = (): boolean => {
    if (!courses.length) {
      setFieldErrors({ courses: t('validation.minOneCourse') })
      return false
    }
    setFieldErrors({})
    return true
  }

  const validateForm = (): boolean => validateBasics() && validateCourses()

  const buildPayload = async (includeSchedule: boolean) => {
    const plannedCourses: PlannedCourse[] = courses.map((course) => ({
      courseId: course.courseId,
      category: 'manual',
    }))

    const semesterPayload: Record<string, unknown> = {
      semesterCode,
      goalCredits: goalCredits ? Number(goalCredits) : totalCredits,
      plannedCourses,
    }

    if (includeSchedule && parsedSemester) {
      semesterPayload.weeklySchedule = {
        entries: courses.map((course) => ({
          courseId: course.courseId,
          academicYear: parsedSemester.academicYear,
          semesterCode: parsedSemester.semesterCode,
        })),
      }
    }

    return {
      name: name.trim(),
      status: 'draft',
      semesters: [semesterPayload],
    }
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!validateForm()) throw new Error('validation')

      await ensurePlanningProfile(
        semesterCode,
        async () => {
          try {
            return await profileApi.get()
          } catch (err) {
            if (isAuthError(err) && err.status === 404) return null
            throw err
          }
        },
        (body) => profileApi.create(body),
      )

      const payload = await buildPayload(scheduleEnabled)

      if (isEdit && planId) {
        return plansApi.update(planId, payload)
      }
      return plansApi.create(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
      const saved = data.semesterPlan
      setPreviewSchedule(saved.semesters[0]?.weeklySchedule)
      navigate(`/plans/${saved.id}`)
    },
    onError: (err) => {
      if (err instanceof Error && err.message === 'validation') return
      setErrors([isAuthError(err) ? err.message : t('common.errorGeneric')])
    },
  })

  const loadScheduleMutation = useMutation({
    mutationFn: async () => {
      if (!validateForm() || !parsedSemester) throw new Error('validation')
      setScheduleEnabled(true)

      await ensurePlanningProfile(
        semesterCode,
        async () => {
          try {
            return await profileApi.get()
          } catch (err) {
            if (isAuthError(err) && err.status === 404) return null
            throw err
          }
        },
        (body) => profileApi.create(body),
      )

      const payload = await buildPayload(true)
      if (isEdit && planId) {
        return plansApi.update(planId, payload)
      }
      return plansApi.create(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
      const saved = data.semesterPlan
      setPreviewSchedule(saved.semesters[0]?.weeklySchedule)
      if (!isEdit) navigate(`/plans/${saved.id}/edit`, { replace: true })
    },
    onError: (err) => {
      if (err instanceof Error && err.message === 'validation') return
      setErrors([isAuthError(err) ? err.message : t('common.errorGeneric')])
    },
  })

  const goNext = () => {
    setErrors([])
    if (step === 'basics') {
      if (!validateBasics()) return
      setStep('courses')
      return
    }
    if (step === 'courses') {
      if (!validateCourses()) return
      setStep('schedule')
    }
  }

  const goBack = () => {
    setErrors([])
    setFieldErrors({})
    if (step === 'courses') setStep('basics')
    else if (step === 'schedule') setStep('courses')
  }

  if (isEdit && planQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Card className="!p-5">
        <p className="mb-4 text-sm text-[var(--color-text-muted)]">{t('plans.standaloneHint')}</p>
        <PlanBuilderStepper step={step} labels={stepLabels} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <div className="space-y-6">
          {step === 'basics' ? (
            <Card>
              <h2 className="text-base font-semibold">{t('plans.stepBasicsTitle')}</h2>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('plans.stepBasicsHint')}</p>

              <div className="mt-6 space-y-6">
                <SemesterPicker
                  value={semesterCode}
                  onChange={setSemesterCode}
                  error={fieldErrors.semesterCode}
                />

                <Input
                  label={t('plans.planName')}
                  value={name}
                  onChange={(e) => {
                    setNameTouched(true)
                    setName(e.target.value)
                  }}
                  error={fieldErrors.name}
                  required
                />

                <div>
                  <Input
                    label={t('plans.goalCredits')}
                    type="number"
                    step="0.5"
                    value={goalCredits}
                    onChange={(e) => setGoalCredits(e.target.value)}
                    error={fieldErrors.goalCredits}
                    className="max-w-xs"
                  />
                  <p className="mt-2 text-xs text-[var(--color-text-muted)]">{t('plans.goalCreditsHint')}</p>
                </div>
              </div>
            </Card>
          ) : null}

          {step === 'courses' ? (
            <Card>
              <h2 className="text-base font-semibold">{t('plans.stepCoursesTitle')}</h2>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('plans.stepCoursesHint')}</p>

              <div className="mt-6 rounded-xl border border-dashed border-[var(--color-primary)]/25 bg-[var(--color-primary)]/5 p-4">
                <CourseSearchCombobox
                  onSelect={addCourse}
                  excludeIds={courses.map((course) => course.courseId)}
                  placeholder={t('plans.searchCourse')}
                  hint={t('plans.searchCourseHint')}
                />
              </div>
              {fieldErrors.courses ? (
                <p className="mt-2 text-xs text-[var(--color-danger)]">{fieldErrors.courses}</p>
              ) : null}

              <div className="mt-6 space-y-3">
                {courses.length ? (
                  courses.map((course, index) => (
                    <div
                      key={course.courseId}
                      className="flex items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-4 py-3"
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-sm font-semibold text-[var(--color-primary)] shadow-sm">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="font-mono text-xs text-[var(--color-primary)]">{course.courseNumber}</p>
                        <p className="truncate text-sm font-medium">{course.courseTitle}</p>
                      </div>
                      <span className="shrink-0 text-sm text-[var(--color-text-muted)]">
                        {formatCredits(course.credits)} {t('common.credits')}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        aria-label={t('plans.removeCourse')}
                        onClick={() => removeCourse(course.courseId)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))
                ) : (
                  <div className="flex flex-col items-center gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-6 py-12 text-center">
                    <BookPlus className="h-10 w-10 text-[var(--color-text-muted)]" />
                    <p className="text-sm font-medium">{t('plans.emptyCoursesTitle')}</p>
                    <p className="max-w-sm text-xs text-[var(--color-text-muted)]">{t('plans.emptyCoursesHint')}</p>
                  </div>
                )}
              </div>
            </Card>
          ) : null}

          {step === 'schedule' ? (
            <>
              <Card>
                <h2 className="text-base font-semibold">{t('plans.stepScheduleTitle')}</h2>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('plans.stepScheduleHint')}</p>

                <ul className="mt-4 space-y-2 text-sm text-[var(--color-text-muted)]">
                  <li className="flex gap-2">
                    <span className="font-semibold text-[var(--color-primary)]">1.</span>
                    {t('plans.scheduleTip1')}
                  </li>
                  <li className="flex gap-2">
                    <span className="font-semibold text-[var(--color-primary)]">2.</span>
                    {t('plans.scheduleTip2')}
                  </li>
                  <li className="flex gap-2">
                    <span className="font-semibold text-[var(--color-primary)]">3.</span>
                    {t('plans.scheduleTip3')}
                  </li>
                </ul>

                <div className="mt-6">
                  <Button
                    variant="secondary"
                    loading={loadScheduleMutation.isPending}
                    disabled={!courses.length}
                    onClick={() => loadScheduleMutation.mutate()}
                  >
                    <Wand2 className="h-4 w-4" />
                    {t('plans.buildSchedule')}
                  </Button>
                </div>
              </Card>

              <Card>
                <h3 className="mb-4 text-sm font-semibold">{t('plans.weeklySchedule')}</h3>
                <WeeklyScheduleView schedule={previewSchedule} />
              </Card>
            </>
          ) : null}

          {errors.length ? (
            <div className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-4 py-3 text-sm text-[var(--color-danger)]">
              {errors.join(' · ')}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-2">
              {step !== 'basics' ? (
                <Button variant="secondary" onClick={goBack}>
                  <ChevronLeft className="h-4 w-4" />
                  {t('plans.back')}
                </Button>
              ) : (
                <Button variant="secondary" onClick={() => navigate('/plans')}>
                  {t('common.cancel')}
                </Button>
              )}
            </div>

            <div className="flex gap-2">
              {step !== 'schedule' ? (
                <Button onClick={goNext}>
                  {t('plans.continue')}
                  <ArrowRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
                  <CalendarPlus className="h-4 w-4" />
                  {t('plans.savePlan')}
                </Button>
              )}
            </div>
          </div>
        </div>

        <PlanBuilderSummary
          className="lg:sticky lg:top-6 lg:self-start"
          name={name}
          semesterCode={semesterCode}
          courseCount={courses.length}
          totalCredits={totalCredits}
          goalCredits={goalNumber}
          stepLabel={`${t('plans.stepOf')} ${step === 'basics' ? 1 : step === 'courses' ? 2 : 3} / 3`}
        />
      </div>
    </div>
  )
}
