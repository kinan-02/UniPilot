import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, BookPlus, CalendarDays, Download, Info, Plus, Redo2, Save, Undo2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { catalogApi, plansApi, profileApi } from '../../api/endpoints'
import { isAuthError } from '../../auth/AuthContext'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { usePlannerHistory } from '../../hooks/usePlannerHistory'
import { useTranslation } from '../../i18n'
import { downloadIcs, generatePlanIcs } from '../../lib/icsExport'
import { ensurePlanningProfile, courseTitle } from '../../lib/planning'
import { courseNumbersInConflict, formatSlotTypes, parseTimeRange } from '../../lib/planner'
import { hasPartialGroupSelection, groupOptionsFromOffering, selectedGroupsSummary } from '../../lib/scheduleGroups'
import {
  defaultSemesterCode,
  parseSemesterCode,
  suggestedPlanName,
} from '../../lib/semester'
import {
  validatePlanName,
  validateSemesterCode,
} from '../../lib/validation'
import type {
  CourseSummary,
  CustomEvent,
  PlannedCourse,
  PlannerInsights,
  SelectedGroups,
  SemesterPlan,
  WeeklySchedule,
} from '../../types/api'
import { formatCredits } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Card, Spinner } from '../ui/Card'
import { Input } from '../ui/Input'
import { CourseDetailModal } from './CourseDetailModal'
import { CourseGroupSelector } from './CourseGroupSelector'
import { CustomEventsPanel } from './CustomEventsPanel'
import { ExamSummaryPanel } from './ExamSummaryPanel'
import { PlannerSummaryBar } from './PlannerSummaryBar'
import { SelectedCourseRow, warningForCourse } from './SelectedCourseRow'
import { SemesterPicker } from './SemesterPicker'
import { SharePlanPanel } from './SharePlanPanel'
import { WeeklyScheduleGrid } from './WeeklyScheduleGrid'

export type DraftCourse = {
  courseId: string
  courseNumber: string
  courseTitle: string
  credits: number
  isActive: boolean
  selectedGroups?: SelectedGroups
  groupSummary?: string
  notes?: string
}

type PlannerSnapshot = {
  courses: DraftCourse[]
  customEvents: CustomEvent[]
}

const emptyPlannerSnapshot = (): PlannerSnapshot => ({ courses: [], customEvents: [] })

type SemesterPlannerProps = {
  planId?: string
}

function mapPlanToDraft(plan: SemesterPlan) {
  const semester = plan.semesters[0]
  return {
    name: plan.name ?? '',
    semesterCode: semester?.semesterCode ?? defaultSemesterCode(),
    courses: (semester?.plannedCourses ?? []).map((course) => ({
      courseId: course.courseId,
      courseNumber: course.courseNumber ?? '',
      courseTitle: course.courseTitle ?? '',
      credits: course.credits ?? 0,
      isActive: course.isActive !== false,
      selectedGroups: course.selectedGroups,
      notes: course.notes,
    })),
    weeklySchedule: semester?.weeklySchedule,
    customEvents: semester?.customEvents ?? semester?.weeklySchedule?.customEvents ?? [],
    plannerInsights: plan.plannerInsights,
  }
}

export function SemesterPlanner({ planId }: SemesterPlannerProps) {
  const { t, locale } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const isEdit = Boolean(planId)

  const planQuery = useQuery({
    queryKey: ['plan', planId],
    queryFn: () => plansApi.get(planId!),
    enabled: isEdit,
  })

  const profileQuery = useQuery({
    queryKey: ['profile'],
    queryFn: () => profileApi.get(),
    retry: false,
  })

  const [name, setName] = useState('')
  const [nameTouched, setNameTouched] = useState(false)
  const [semesterCode, setSemesterCode] = useState(defaultSemesterCode())
  const {
    present: plannerState,
    setPresent: setPlannerState,
    reset: resetPlanner,
    undo: undoPlanner,
    redo: redoPlanner,
    canUndo,
    canRedo,
  } = usePlannerHistory<PlannerSnapshot>(emptyPlannerSnapshot())
  const courses = plannerState.courses
  const customEvents = plannerState.customEvents
  const setCourses = (
    updater: DraftCourse[] | ((prev: DraftCourse[]) => DraftCourse[]),
  ) => {
    setPlannerState((prev) => ({
      ...prev,
      courses: typeof updater === 'function' ? updater(prev.courses) : updater,
    }))
  }
  const setCustomEvents = (
    updater: CustomEvent[] | ((prev: CustomEvent[]) => CustomEvent[]),
  ) => {
    setPlannerState((prev) => ({
      ...prev,
      customEvents: typeof updater === 'function' ? updater(prev.customEvents) : updater,
    }))
  }
  const [customEventsDirty, setCustomEventsDirty] = useState(false)
  const [weeklySchedule, setWeeklySchedule] = useState<WeeklySchedule | undefined>()
  const [plannerInsights, setPlannerInsights] = useState<PlannerInsights | undefined>()
  const [searchQuery, setSearchQuery] = useState('')
  const [facultyFilter, setFacultyFilter] = useState('')
  const [minCredits, setMinCredits] = useState('')
  const [maxCredits, setMaxCredits] = useState('')
  const [slotTypeFilter, setSlotTypeFilter] = useState('')
  const [detailCourseNumber, setDetailCourseNumber] = useState<string | null>(null)
  const [previewCourseNumber, setPreviewCourseNumber] = useState<string | null>(null)
  const [groupSelectorCourse, setGroupSelectorCourse] = useState<DraftCourse | null>(null)
  const [hideSelectedInSearch, setHideSelectedInSearch] = useState(true)
  const [scheduleRevealed, setScheduleRevealed] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300)
  const parsedSemester = parseSemesterCode(semesterCode)
  const semesterSelected = Boolean(parsedSemester)

  useEffect(() => {
    if (!planQuery.data?.semesterPlan) return
    const draft = mapPlanToDraft(planQuery.data.semesterPlan)
    setName(draft.name)
    setNameTouched(true)
    setSemesterCode(draft.semesterCode)
    resetPlanner({ courses: draft.courses, customEvents: draft.customEvents })
    setWeeklySchedule(draft.weeklySchedule)
    setPlannerInsights(draft.plannerInsights)
  }, [planQuery.data])

  useEffect(() => {
    if (nameTouched) return
    setName(suggestedPlanName(semesterCode, locale))
  }, [semesterCode, locale, nameTouched])

  const activeCourses = useMemo(
    () => courses.filter((course) => course.isActive !== false),
    [courses],
  )

  const totalCredits = useMemo(
    () => activeCourses.reduce((sum, course) => sum + (course.credits || 0), 0),
    [activeCourses],
  )

  const conflictNumbers = useMemo(
    () => courseNumbersInConflict(weeklySchedule),
    [weeklySchedule],
  )

  const examCount = plannerInsights?.examSummary?.totalExams ?? plannerInsights?.examSummary?.exams?.length ?? 0
  const conflictCount = plannerInsights?.scheduleConflicts?.length ?? weeklySchedule?.conflicts?.length ?? 0

  const maxCreditsPref =
    plannerInsights?.maxCreditsPerSemester ??
    profileQuery.data?.profile.preferences?.maxCreditsPerSemester

  const searchParams = useMemo(() => {
    if (!parsedSemester || debouncedSearch.length < 2) return null
    const params: Record<string, string | number | boolean> = {
      q: debouncedSearch,
      limit: 20,
      offset: 0,
      academicYear: parsedSemester.academicYear,
      semesterCode: parsedSemester.semesterCode,
    }
    if (/^0\d{7}$/.test(debouncedSearch)) params.courseNumber = debouncedSearch
    if (facultyFilter.trim()) params.faculty = facultyFilter.trim()
    if (minCredits) params.minCredits = Number(minCredits)
    if (maxCredits) params.maxCredits = Number(maxCredits)
    return params
  }, [debouncedSearch, parsedSemester, facultyFilter, minCredits, maxCredits])

  const searchResultsQuery = useQuery({
    queryKey: ['planner-search', searchParams],
    queryFn: () => catalogApi.courses(searchParams!),
    enabled: Boolean(searchParams),
  })

  const patchCourseMutation = useMutation({
    mutationFn: (body: {
      courseNumber: string
      isActive?: boolean
      selectedGroups?: SelectedGroups
    }) =>
      plansApi.patchCourse(planId!, body.courseNumber, {
        ...(body.isActive !== undefined ? { isActive: body.isActive } : {}),
        ...(body.selectedGroups !== undefined ? { selectedGroups: body.selectedGroups } : {}),
      }),
    onSuccess: (data) => {
      setWeeklySchedule(data.semesterPlan.semesters[0]?.weeklySchedule)
      setPlannerInsights(data.semesterPlan.plannerInsights)
      queryClient.invalidateQueries({ queryKey: ['plan', planId] })
    },
  })

  const reorderMutation = useMutation({
    mutationFn: (courseIds: string[]) => plansApi.reorderCourses(planId!, courseIds),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan', planId] }),
  })

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
        isActive: true,
      },
    ])
  }

  const toggleCourseActive = (courseId: string) => {
    setCourses((prev) => {
      const next = prev.map((course) =>
        course.courseId === courseId ? { ...course, isActive: !course.isActive } : course,
      )
      const target = next.find((course) => course.courseId === courseId)
      if (planId && target) {
        patchCourseMutation.mutate({
          courseNumber: target.courseNumber,
          isActive: target.isActive,
        })
      }
      return next
    })
  }

  const moveCourse = (courseId: string, direction: -1 | 1) => {
    setCourses((prev) => {
      const index = prev.findIndex((course) => course.courseId === courseId)
      if (index < 0) return prev
      const nextIndex = index + direction
      if (nextIndex < 0 || nextIndex >= prev.length) return prev
      const copy = [...prev]
      const [item] = copy.splice(index, 1)
      copy.splice(nextIndex, 0, item)
      if (planId) {
        reorderMutation.mutate(copy.map((course) => course.courseId))
      }
      return copy
    })
  }

  const removeCourse = (courseId: string) => {
    setCourses((prev) => prev.filter((course) => course.courseId !== courseId))
  }

  const saveSelectedGroups = async (courseNumber: string, selectedGroups: SelectedGroups) => {
    let groupSummary = ''
    if (parsedSemester && hasPartialGroupSelection(selectedGroups)) {
      try {
        const offeringData = await catalogApi.offerings(courseNumber, {
          academicYear: parsedSemester.academicYear,
          semesterCode: parsedSemester.semesterCode,
        })
        const options = groupOptionsFromOffering(offeringData.offerings?.[0]?.scheduleGroups ?? [])
        groupSummary = selectedGroupsSummary(selectedGroups, options)
      } catch {
        groupSummary = t('planner.customGroupsSet')
      }
    }

    setCourses((prev) =>
      prev.map((course) =>
        course.courseNumber === courseNumber
          ? { ...course, selectedGroups, groupSummary: groupSummary || undefined }
          : course,
      ),
    )
    if (planId) {
      patchCourseMutation.mutate({ courseNumber, selectedGroups })
    }
    setGroupSelectorCourse(null)
  }

  const exportIcs = () => {
    const content = generatePlanIcs({
      planName: name.trim() || t('plans.newPlan'),
      schedule: weeklySchedule,
      examSummary: plannerInsights?.examSummary,
      customEvents,
    })
    const safeName = (name.trim() || 'semester-plan').replace(/[^\w-]+/g, '-').slice(0, 40)
    downloadIcs(content, `${safeName}.ics`)
  }

  const validateForm = (): boolean => {
    const nextFieldErrors: Record<string, string> = {}
    const nameResult = validatePlanName(name)
    if (!nameResult.ok) nextFieldErrors.name = t(nameResult.message)

    const semesterResult = validateSemesterCode(semesterCode)
    if (!semesterResult.ok) nextFieldErrors.semesterCode = t(semesterResult.message)

    if (!courses.length) nextFieldErrors.courses = t('validation.minOneCourse')

    setFieldErrors(nextFieldErrors)
    return Object.keys(nextFieldErrors).length === 0
  }

  const buildPayload = (includeSchedule: boolean) => {
    const plannedCourses: PlannedCourse[] = courses.map((course) => ({
      courseId: course.courseId,
      category: 'manual',
      isActive: course.isActive,
      selectedGroups: course.selectedGroups,
      notes: course.notes,
    }))

    const semesterPayload: Record<string, unknown> = {
      semesterCode,
      goalCredits: totalCredits,
      plannedCourses,
      customEvents,
    }

    if (includeSchedule && parsedSemester) {
      semesterPayload.weeklySchedule = {
        entries: activeCourses.map((course) => ({
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

      const payload = buildPayload(true)
      if (isEdit && planId) return plansApi.update(planId, payload)
      return plansApi.create(payload)
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
      const saved = data.semesterPlan
      setWeeklySchedule(saved.semesters[0]?.weeklySchedule)
      setPlannerInsights(saved.plannerInsights)
      navigate(`/plans/${saved.id}`)
    },
    onError: (err) => {
      if (err instanceof Error && err.message === 'validation') return
      setErrors([isAuthError(err) ? err.message : t('common.errorGeneric')])
    },
  })

  const refreshScheduleMutation = useMutation({
    mutationFn: async () => {
      if (!validateForm()) throw new Error('validation')
      const payload = buildPayload(true)
      if (isEdit && planId) return plansApi.update(planId, payload)
      return plansApi.create(payload)
    },
    onSuccess: (data) => {
      setWeeklySchedule(data.semesterPlan.semesters[0]?.weeklySchedule)
      setPlannerInsights(data.semesterPlan.plannerInsights)
      setScheduleRevealed(true)
      setCustomEventsDirty(false)
      if (!isEdit && data.semesterPlan.id) {
        navigate(`/plans/${data.semesterPlan.id}/edit`, { replace: true })
      }
    },
  })

  const handleBuildSchedule = () => {
    if (!activeCourses.length) return
    refreshScheduleMutation.mutate()
  }

  const slotTypeMatches = (slotTypes: string[] | undefined, filter: string) => {
    if (!filter) return true
    const normalized = (slotTypes ?? []).map((value) => value.toLowerCase())
    const aliases: Record<string, string[]> = {
      lecture: ['lecture', 'הרצאה', 'lec'],
      tutorial: ['tutorial', 'תרגול', 'recitation'],
      lab: ['lab', 'מעבדה'],
    }
    const targets = aliases[filter] ?? [filter]
    return normalized.some((value) => targets.some((target) => value.includes(target)))
  }

  const searchItems = useMemo(() => {
    let items = searchResultsQuery.data?.items ?? []
    if (hideSelectedInSearch) {
      items = items.filter(
        (course) => course.id && !courses.some((selected) => selected.courseId === course.id),
      )
    }
    if (slotTypeFilter) {
      items = items.filter((course) =>
        slotTypeMatches(course.semesterOfferingSummary?.slotTypes, slotTypeFilter),
      )
    }
    return items
  }, [searchResultsQuery.data?.items, hideSelectedInSearch, courses, slotTypeFilter])

  const previewOfferingQuery = useQuery({
    queryKey: ['preview-offering', previewCourseNumber, parsedSemester?.academicYear, parsedSemester?.semesterCode],
    queryFn: () =>
      catalogApi.offerings(previewCourseNumber!, {
        academicYear: parsedSemester!.academicYear,
        semesterCode: parsedSemester!.semesterCode,
      }),
    enabled: Boolean(previewCourseNumber && parsedSemester && scheduleRevealed),
  })

  const previewEvents = useMemo(() => {
    if (!previewCourseNumber || !previewOfferingQuery.data?.offerings?.length) return []
    const offering = previewOfferingQuery.data.offerings[0]
    const title =
      searchItems.find((item) => item.courseNumber === previewCourseNumber)?.titleHebrew ??
      previewCourseNumber
    return (offering.scheduleGroups ?? []).flatMap((group) => {
      const day = group.day || group.יום || ''
      const time = group.time || group.שעה || ''
      const parsed = parseTimeRange(time.replace(/[–—]/g, '-'))
      if (!day || !parsed) return []
      return [
        {
          day,
          timeRange: time,
          slotType: group.type || group.סוג,
          courseNumber: previewCourseNumber,
          courseTitle: `${title} (${t('planner.preview')})`,
          startMinutes: parsed.start,
          endMinutes: parsed.end,
        },
      ]
    })
  }, [previewCourseNumber, previewOfferingQuery.data, searchItems, t])

  if (isEdit && planQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 shadow-[var(--shadow-soft)]">
        <div className="min-w-0 flex-1">
          <SemesterPicker
            compact
            value={semesterCode}
            onChange={setSemesterCode}
            error={fieldErrors.semesterCode}
          />
        </div>
        <Input
          label={t('plans.planName')}
          value={name}
          onChange={(e) => {
            setNameTouched(true)
            setName(e.target.value)
          }}
          error={fieldErrors.name}
          required
          className="h-9 max-w-[220px] text-sm"
        />
        <div className="flex gap-1">
          <Button variant="ghost" size="sm" disabled={!canUndo} onClick={undoPlanner} aria-label={t('planner.undo')}>
            <Undo2 className="h-4 w-4" />
          </Button>
          <Button variant="ghost" size="sm" disabled={!canRedo} onClick={redoPlanner} aria-label={t('planner.redo')}>
            <Redo2 className="h-4 w-4" />
          </Button>
          {scheduleRevealed ? (
            <Button variant="ghost" size="sm" onClick={exportIcs} aria-label={t('planner.exportIcs')}>
              <Download className="h-4 w-4" />
            </Button>
          ) : null}
        </div>
      </div>

      <PlannerSummaryBar
        activeCount={activeCourses.length}
        totalCount={courses.length}
        activeCredits={totalCredits}
        conflictCount={conflictCount}
        examCount={examCount}
        maxCredits={maxCreditsPref}
      />

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <div className="space-y-6">
          <Card>
            <h2 className="text-base font-semibold">{t('planner.searchTitle')}</h2>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('planner.searchHint')}</p>

            {!semesterSelected ? (
              <p className="mt-6 rounded-xl border border-dashed border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
                {t('planner.selectSemesterFirst')}
              </p>
            ) : (
              <>
                <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Input
                    label={t('common.search')}
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={t('plans.searchCourse')}
                  />
                  <Input
                    label={t('catalog.faculty')}
                    value={facultyFilter}
                    onChange={(e) => setFacultyFilter(e.target.value)}
                    placeholder={t('catalog.allFaculties')}
                  />
                  <Input
                    label={t('planner.minCredits')}
                    type="number"
                    step="0.5"
                    value={minCredits}
                    onChange={(e) => setMinCredits(e.target.value)}
                  />
                  <Input
                    label={t('planner.maxCreditsFilter')}
                    type="number"
                    step="0.5"
                    value={maxCredits}
                    onChange={(e) => setMaxCredits(e.target.value)}
                  />
                </div>

                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="block space-y-1.5">
                    <span className="text-sm font-medium">{t('planner.slotTypeFilter')}</span>
                    <select
                      className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm"
                      value={slotTypeFilter}
                      onChange={(e) => setSlotTypeFilter(e.target.value)}
                    >
                      <option value="">{t('planner.slotTypeAll')}</option>
                      <option value="lecture">{t('planner.slot.lecture')}</option>
                      <option value="tutorial">{t('planner.slot.tutorial')}</option>
                      <option value="lab">{t('planner.slot.lab')}</option>
                    </select>
                  </label>
                  <label className="flex items-end gap-2 pb-2 text-sm text-[var(--color-text-muted)]">
                    <input
                      type="checkbox"
                      checked={hideSelectedInSearch}
                      onChange={(e) => setHideSelectedInSearch(e.target.checked)}
                      className="rounded border-[var(--color-border)]"
                    />
                    {t('planner.hideSelected')}
                  </label>
                </div>

                <div className="mt-4 space-y-2">
                  {searchResultsQuery.isLoading ? (
                    <div className="flex justify-center py-8">
                      <Spinner />
                    </div>
                  ) : debouncedSearch.length < 2 ? (
                    <p className="text-sm text-[var(--color-text-muted)]">{t('plans.searchCourseHint')}</p>
                  ) : searchResultsQuery.isError ? (
                    <p className="text-sm text-[var(--color-danger)]">{t('common.errorGeneric')}</p>
                  ) : searchItems.length ? (
                    searchItems.map((course) => (
                      <div
                        key={course.id}
                        tabIndex={0}
                        onMouseEnter={() => setPreviewCourseNumber(course.courseNumber)}
                        onMouseLeave={() => setPreviewCourseNumber(null)}
                        onFocus={() => setPreviewCourseNumber(course.courseNumber)}
                        onBlur={() => setPreviewCourseNumber(null)}
                        className={`flex flex-wrap items-center gap-3 rounded-xl border px-4 py-3 transition ${
                          previewCourseNumber === course.courseNumber
                            ? 'border-[var(--color-primary)]/40 bg-[var(--color-primary)]/5'
                            : 'border-[var(--color-border)] bg-[var(--color-surface-muted)]'
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="font-mono text-xs text-[var(--color-primary)]">{course.courseNumber}</p>
                          <p className="truncate text-sm font-medium">{courseTitle(course, locale)}</p>
                          <p className="text-xs text-[var(--color-text-muted)]">
                            {[course.faculty, course.credits != null ? formatCredits(course.credits) : null]
                              .filter(Boolean)
                              .join(' · ')}
                            {course.semesterOfferingSummary?.slotTypes?.length
                              ? ` · ${formatSlotTypes(course.semesterOfferingSummary.slotTypes)}`
                              : ''}
                          </p>
                        </div>
                        <Button variant="ghost" size="sm" onClick={() => setDetailCourseNumber(course.courseNumber)}>
                          <Info className="h-4 w-4" />
                        </Button>
                        <Button size="sm" onClick={() => addCourse(course)}>
                          <Plus className="h-4 w-4" />
                          {t('catalog.addToPlan')}
                        </Button>
                      </div>
                    ))
                  ) : (
                    <p className="rounded-xl border border-[var(--color-border)] px-4 py-8 text-center text-sm text-[var(--color-text-muted)]">
                      {t('planner.noCoursesSemester')}
                    </p>
                  )}
                </div>
              </>
            )}
          </Card>

          <Card>
            {!scheduleRevealed ? (
              <div className="flex flex-col items-center gap-3 py-6 text-center">
                <CalendarDays className="h-9 w-9 text-[var(--color-text-muted)]" />
                <div>
                  <h3 className="text-sm font-semibold">{t('plans.weeklySchedule')}</h3>
                  <p className="mt-1 max-w-sm text-xs text-[var(--color-text-muted)]">
                    {t('planner.scheduleHiddenHint')}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  loading={refreshScheduleMutation.isPending}
                  disabled={!activeCourses.length}
                  onClick={handleBuildSchedule}
                >
                  <CalendarDays className="h-4 w-4" />
                  {t('plans.buildSchedule')}
                </Button>
              </div>
            ) : (
              <>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold">{t('plans.weeklySchedule')}</h3>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setScheduleRevealed(false)}
                    >
                      {t('planner.hideSchedule')}
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={refreshScheduleMutation.isPending}
                      disabled={!activeCourses.length}
                      onClick={handleBuildSchedule}
                    >
                      {t('planner.rebuildSchedule')}
                    </Button>
                  </div>
                </div>
                <WeeklyScheduleGrid
                  schedule={weeklySchedule}
                  previewEvents={previewEvents}
                  customEvents={customEvents}
                />
              </>
            )}
          </Card>

          {scheduleRevealed ? (
            <CustomEventsPanel
              events={customEvents}
              onChange={(events) => {
                setCustomEvents(events)
                setCustomEventsDirty(true)
              }}
            />
          ) : null}

          {scheduleRevealed && customEventsDirty ? (
            <p className="text-xs text-[var(--color-warning)]">{t('planner.customEventsRebuildHint')}</p>
          ) : null}

          <ExamSummaryPanel summary={plannerInsights?.examSummary} />
        </div>

        <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
          <Card>
            <h3 className="text-sm font-semibold">{t('plans.selectedCourses')}</h3>
            <div className="mt-3 flex flex-wrap items-baseline justify-between gap-2">
              <p className="text-2xl font-semibold text-[var(--color-primary)]">
                {formatCredits(totalCredits)} {t('common.credits')}
              </p>
              {maxCreditsPref != null ? (
                <p
                  className={`text-xs ${
                    totalCredits > maxCreditsPref
                      ? 'text-[var(--color-warning)]'
                      : 'text-[var(--color-text-muted)]'
                  }`}
                >
                  {t('planner.maxCreditsPref')}: {maxCreditsPref}
                </p>
              ) : null}
            </div>

            {plannerInsights?.creditsWarning ? (
              <p className="mt-2 flex items-start gap-2 text-xs text-[var(--color-warning)]">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                {plannerInsights.creditsWarning.message}
              </p>
            ) : null}

            <div className="mt-4 space-y-2">
              {courses.length ? (
                courses.map((course, index) => (
                  <SelectedCourseRow
                    key={course.courseId}
                    course={course}
                    index={index}
                    total={courses.length}
                    conflict={conflictNumbers.has(course.courseNumber)}
                    prereqWarning={warningForCourse(plannerInsights, course.courseId)}
                    staleWarning={
                      plannerInsights?.staleCourseWarnings?.find(
                        (w) => w.courseNumber === course.courseNumber,
                      )?.message
                    }
                    groupsSummary={
                      course.groupSummary ||
                      (hasPartialGroupSelection(course.selectedGroups)
                        ? t('planner.customGroupsSet')
                        : undefined)
                    }
                    onToggleActive={() => toggleCourseActive(course.courseId)}
                    onRemove={() => removeCourse(course.courseId)}
                    onInfo={() => setDetailCourseNumber(course.courseNumber)}
                    onEditGroups={
                      semesterSelected
                        ? () => setGroupSelectorCourse(course)
                        : undefined
                    }
                    onMoveUp={() => moveCourse(course.courseId, -1)}
                    onMoveDown={() => moveCourse(course.courseId, 1)}
                  />
                ))
              ) : (
                <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-[var(--color-border)] px-4 py-10 text-center">
                  <BookPlus className="h-8 w-8 text-[var(--color-text-muted)]" />
                  <p className="text-sm font-medium">{t('plans.emptyCoursesTitle')}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">{t('plans.emptyCoursesHint')}</p>
                </div>
              )}
            </div>
            {fieldErrors.courses ? (
              <p className="mt-2 text-xs text-[var(--color-danger)]">{fieldErrors.courses}</p>
            ) : null}
          </Card>

          {errors.length ? (
            <div className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-4 py-3 text-sm text-[var(--color-danger)]">
              {errors.join(' · ')}
            </div>
          ) : null}

          {planId ? (
            <SharePlanPanel
              planId={planId}
              plan={{
                shareEnabled: planQuery.data?.semesterPlan.shareEnabled,
                shareToken: planQuery.data?.semesterPlan.shareToken,
                status: planQuery.data?.semesterPlan.status,
              }}
            />
          ) : null}

          <Button className="w-full" loading={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            <Save className="h-4 w-4" />
            {t('plans.savePlan')}
          </Button>
        </aside>
      </div>

      <CourseDetailModal
        courseNumber={detailCourseNumber}
        academicYear={parsedSemester?.academicYear}
        semesterCode={parsedSemester?.semesterCode}
        onClose={() => setDetailCourseNumber(null)}
      />

      {groupSelectorCourse && parsedSemester ? (
        <CourseGroupSelector
          courseNumber={groupSelectorCourse.courseNumber}
          courseTitle={groupSelectorCourse.courseTitle}
          academicYear={parsedSemester.academicYear}
          semesterCode={parsedSemester.semesterCode}
          selectedGroups={groupSelectorCourse.selectedGroups}
          onClose={() => setGroupSelectorCourse(null)}
          onSave={(groups) => saveSelectedGroups(groupSelectorCourse.courseNumber, groups)}
        />
      ) : null}
    </div>
  )
}
