import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { catalogApi, plansApi } from '../../api/endpoints'
import { isAuthError } from '../../auth/AuthContext'
import { useClientSchedulePreview } from '../../hooks/useClientSchedulePreview'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { usePlannerHistory } from '../../hooks/usePlannerHistory'
import { useTranslation } from '../../i18n'
import { downloadIcs, generatePlanIcs } from '../../lib/icsExport'
import { ensurePlanningProfile, PlanningProfileError, courseTitle } from '../../lib/planning'
import { fetchStudentProfileOrNull, useStudentProfileQuery } from '../../lib/studentProfileQuery'
import { courseNumbersInConflict } from '../../lib/planner'
import {
  extractLessonOptions,
  hasLessonSelection,
  lessonSelectionSummary,
  toggleLessonSelection,
} from '../../lib/lessonEvents'
import { buildScheduleGridEvents } from '../../lib/scheduleGridEvents'
import {
  defaultSemesterCode,
  parseSemesterCode,
  pickDefaultPlannerSemester,
  suggestedPlanName,
} from '../../lib/semester'
import { formatCredits } from '../../lib/utils'
import {
  validatePlanName,
  validateSemesterCode,
} from '../../lib/validation'
import type {
  CourseSummary,
  CustomEvent,
  PlannedCourse,
  PlannerInsights,
  SelectedLessonEvent,
  SemesterPlan,
  WeeklySchedule,
} from '../../types/api'
import { Card, Spinner } from '../ui/Card'
import { buildPlanChanges } from '../../lib/plannerChanges'
import {
  formatAutoPickStatus,
  mergeSuggestedCourses,
  type CourseSuggestionExplanation,
} from '../../lib/plannerAutoAssist'
import {
  addMaybeCourseToSnapshot,
  filterSearchItemsForPlanner,
  buildMaybePersistSignature,
  buildSelectedPersistSignature,
  draftCoursesFromPlanned,
  hydratePlannerFromServer,
  isCourseInPlannerLists,
  moveMaybeToSelectedSnapshot,
  moveSelectedToMaybeSnapshot,
  plannedCoursesForSave,
  removeMaybeCourseFromSnapshot,
  updateMaybeCourseLessons,
} from '../../lib/plannerMaybeCourses'
import {
  emptyPlannerFilters,
  type DraftCourse,
  type PlannerFilters,
  type PlannerSnapshot,
} from '../../types/planner'
import { ChangesDialog } from './ChangesDialog'
import { PlannerAutoAssistPanel } from './PlannerAutoAssistPanel'
import { PlannerCourseSearch } from './PlannerCourseSearch'
import { PlannerTopBar } from './PlannerTopBar'
import { CustomEventsPanel } from './CustomEventsPanel'
import { ExamSummaryPanel } from './ExamSummaryPanel'
import { PlannerSummaryBar } from './PlannerSummaryBar'
import { MaybeCoursesPanel } from './MaybeCoursesPanel'
import { SelectedCourseListItem } from './SelectedCourseListItem'
import { SelectedCoursesPanel } from './SelectedCoursesPanel'
import { SharePlanPanel } from './SharePlanPanel'
import { CourseDetailModal } from './CourseDetailModal'
import { WeeklyScheduleGrid } from './WeeklyScheduleGrid'

export type { DraftCourse } from '../../types/planner'

const emptyPlannerSnapshot = (): PlannerSnapshot => ({
  courses: [],
  maybeCourses: [],
  customEvents: [],
})

function draftFromCourseSummary(course: CourseSummary, locale: 'he' | 'en'): DraftCourse {
  return {
    courseId: course.id!,
    courseNumber: course.courseNumber,
    courseTitle: courseTitle(course, locale),
    credits: course.credits ?? 0,
    isActive: true,
  }
}

type SemesterPlannerProps = {
  planId?: string
}

function mapPlanToDraft(plan: SemesterPlan) {
  const semester = plan.semesters[0]
  return {
    name: plan.name ?? '',
    semesterCode: semester?.semesterCode ?? defaultSemesterCode(),
    courses: draftCoursesFromPlanned(semester?.plannedCourses ?? []),
    maybeCourses: draftCoursesFromPlanned(semester?.maybeCourses ?? []),
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

  const profileQuery = useStudentProfileQuery()

  const plannerSemestersQuery = useQuery({
    queryKey: ['catalog', 'planner-semesters'],
    queryFn: async () => {
      const response = await catalogApi.plannerSemesters()
      return response.planSemesterCodes
    },
  })
  const plannerSemesterOptions = plannerSemestersQuery.data ?? []

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
  const maybeCourses = plannerState.maybeCourses
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
  const [filters, setFilters] = useState<PlannerFilters>(emptyPlannerFilters())
  const [filtersExpanded, setFiltersExpanded] = useState(false)
  const [highlightedCourseNumber, setHighlightedCourseNumber] = useState<string | null>(null)
  const [conflictHighlightNumbers, setConflictHighlightNumbers] = useState<Set<string> | null>(null)
  const [showChangesDialog, setShowChangesDialog] = useState(false)
  const [focusedCourseNumber, setFocusedCourseNumber] = useState<string | null>(null)
  const [hoveredLessonEventId, setHoveredLessonEventId] = useState<string | null>(null)
  const [detailCourseNumber, setDetailCourseNumber] = useState<string | null>(null)
  const [persistedCourseIds, setPersistedCourseIds] = useState<Set<string>>(() => new Set())
  const [persistedSelectedSignature, setPersistedSelectedSignature] = useState('')
  const [persistedMaybeSignature, setPersistedMaybeSignature] = useState('')
  const skipAutoInsightsRef = useRef(true)
  const lessonPatchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const maybeLessonPatchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const hydratedPlanIdRef = useRef<string | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [autoAssistStatus, setAutoAssistStatus] = useState('')
  const [autoAssistStatusTone, setAutoAssistStatusTone] = useState<'success' | 'warning'>('success')
  const [autoAssistError, setAutoAssistError] = useState('')

  const debouncedSearch = useDebouncedValue(searchQuery.trim(), 300)
  const parsedSemester = parseSemesterCode(semesterCode)
  const semesterSelected = Boolean(parsedSemester)

  useEffect(() => {
    if (!planId) {
      hydratedPlanIdRef.current = null
      return
    }
    if (!planQuery.data?.semesterPlan) return
    if (hydratedPlanIdRef.current === planId) return

    hydratedPlanIdRef.current = planId
    const draft = mapPlanToDraft(planQuery.data.semesterPlan)
    setName(draft.name)
    setNameTouched(true)
    setSemesterCode(draft.semesterCode)
    resetPlanner({
      courses: draft.courses,
      maybeCourses: draft.maybeCourses,
      customEvents: draft.customEvents,
    })
    setWeeklySchedule(draft.weeklySchedule)
    setPlannerInsights(draft.plannerInsights)
    setPersistedCourseIds(new Set(draft.courses.map((course) => course.courseId)))
    setPersistedSelectedSignature(buildSelectedPersistSignature(draft.courses))
    setPersistedMaybeSignature(buildMaybePersistSignature(draft.maybeCourses))
    setCustomEventsDirty(false)
    skipAutoInsightsRef.current = true
    queueMicrotask(() => {
      skipAutoInsightsRef.current = false
    })
  }, [planId, planQuery.data?.semesterPlan, resetPlanner])

  useEffect(() => {
    if (nameTouched) return
    setName(suggestedPlanName(semesterCode, locale))
  }, [semesterCode, locale, nameTouched])

  useEffect(() => {
    if (isEdit || plannerSemestersQuery.isLoading) return
    if (!plannerSemesterOptions.length) return
    if (!plannerSemesterOptions.includes(semesterCode)) {
      setSemesterCode(pickDefaultPlannerSemester(plannerSemesterOptions))
    }
  }, [isEdit, plannerSemestersQuery.isLoading, plannerSemesterOptions, semesterCode])

  const activeCourses = useMemo(
    () => courses.filter((course) => course.isActive !== false),
    [courses],
  )

  const selectedPersistSignature = useMemo(
    () => buildSelectedPersistSignature(courses),
    [courses],
  )

  const maybePersistSignature = useMemo(
    () => buildMaybePersistSignature(maybeCourses),
    [maybeCourses],
  )

  const selectedPersistSignatureRef = useRef(selectedPersistSignature)
  selectedPersistSignatureRef.current = selectedPersistSignature

  const maybePersistSignatureRef = useRef(maybePersistSignature)
  maybePersistSignatureRef.current = maybePersistSignature

  const activeMaybeCourses = useMemo(
    () => maybeCourses.filter((course) => course.isActive !== false),
    [maybeCourses],
  )

  const previewCourses = useMemo(
    () =>
      [...activeCourses, ...activeMaybeCourses].map((course) => ({
        courseNumber: course.courseNumber,
        courseTitle: course.courseTitle,
        isActive: course.isActive,
        selectedGroups: course.selectedGroups,
        selectedLessonEvents: course.selectedLessonEvents,
      })),
    [activeCourses, activeMaybeCourses],
  )

  const clientPreviewQuery = useClientSchedulePreview({
    courses: previewCourses,
    academicYear: parsedSemester?.academicYear,
    semesterCode: parsedSemester?.semesterCode,
    customEvents,
  })

  const displaySchedule = useMemo(() => {
    const hasDraftCourses = previewCourses.length > 0
    // Live draft: never fall back to persisted server schedule (it can be stale after removals).
    if (hasDraftCourses) {
      return clientPreviewQuery.data?.schedule
    }
    if (weeklySchedule?.weekView?.length) {
      return weeklySchedule
    }
    return clientPreviewQuery.data?.schedule
  }, [previewCourses.length, clientPreviewQuery.data?.schedule, weeklySchedule])

  const totalCredits = useMemo(
    () => activeCourses.reduce((sum, course) => sum + (course.credits || 0), 0),
    [activeCourses],
  )

  const conflictNumbers = useMemo(
    () => courseNumbersInConflict(displaySchedule),
    [displaySchedule],
  )

  const displayExamSummary = useMemo(() => {
    if (clientPreviewQuery.data?.examSummary) {
      return clientPreviewQuery.data.examSummary
    }
    return plannerInsights?.examSummary
  }, [clientPreviewQuery.data?.examSummary, plannerInsights?.examSummary])

  const examCount = displayExamSummary?.totalExams ?? displayExamSummary?.exams?.length ?? 0
  const conflictCount =
    displaySchedule?.conflicts?.length ?? plannerInsights?.scheduleConflicts?.length ?? 0

  const maxCreditsPref =
    plannerInsights?.maxCreditsPerSemester ??
    profileQuery.data?.profile.preferences?.maxCreditsPerSemester

  const searchMinLength = /^0\d*$/.test(debouncedSearch) ? 1 : 2

  const searchParams = useMemo(() => {
    if (!parsedSemester || debouncedSearch.length < searchMinLength) return null
    const params: Record<string, string | number | boolean> = {
      q: debouncedSearch,
      limit: 20,
      offset: 0,
      academicYear: parsedSemester.academicYear,
      semesterCode: parsedSemester.semesterCode,
    }
    if (/^0\d{7}$/.test(debouncedSearch)) params.courseNumber = debouncedSearch
    if (filters.faculty.trim()) params.faculty = filters.faculty.trim()
    if (filters.minCredits) params.minCredits = Number(filters.minCredits)
    if (filters.maxCredits) params.maxCredits = Number(filters.maxCredits)
    return params
  }, [debouncedSearch, searchMinLength, parsedSemester, filters])

  const searchResultsQuery = useQuery({
    queryKey: ['planner-search', searchParams],
    queryFn: () => catalogApi.courses(searchParams!),
    enabled: Boolean(searchParams),
  })

  const syncFromSavedPlan = (plan: SemesterPlan) => {
    const semester = plan.semesters[0]
    const savedCourses = draftCoursesFromPlanned(semester?.plannedCourses ?? [])
    const savedMaybeCourses = draftCoursesFromPlanned(semester?.maybeCourses ?? [])
    resetPlanner(
      hydratePlannerFromServer(
        {
          courses: [],
          maybeCourses: [],
          customEvents: semester?.customEvents ?? semester?.weeklySchedule?.customEvents ?? [],
        },
        savedCourses,
        savedMaybeCourses,
      ),
    )
    setWeeklySchedule(semester?.weeklySchedule)
    setPlannerInsights(plan.plannerInsights)
    setPersistedCourseIds(new Set(savedCourses.map((course) => course.courseId)))
    setPersistedSelectedSignature(buildSelectedPersistSignature(savedCourses))
    setPersistedMaybeSignature(buildMaybePersistSignature(savedMaybeCourses))
    setCustomEventsDirty(false)
    skipAutoInsightsRef.current = true
    queueMicrotask(() => {
      skipAutoInsightsRef.current = false
    })
  }

  const handlePlannerMutationError = (err: unknown) => {
    setErrors([isAuthError(err) ? err.message : t('common.errorGeneric')])
  }

  const lessonSelectionMutation = useMutation({
    mutationFn: (body: {
      courseNumber: string
      selectedLessonEvents: SelectedLessonEvent[]
    }) =>
      plansApi.patchLessonSelection(planId!, body.courseNumber, {
        selectedLessonEvents: body.selectedLessonEvents,
      }),
    onSuccess: (data) => {
      const semester = data.semesterPlan.semesters[0]
      setWeeklySchedule(semester?.weeklySchedule)
      queryClient.setQueryData(['plan', planId], data)
    },
    onError: handlePlannerMutationError,
  })

  const isCourseInPlanner = (courseId: string) =>
    isCourseInPlannerLists(courses, maybeCourses, courseId)

  const addCourse = (course: CourseSummary) => {
    if (!course.id) return
    if (isCourseInPlanner(course.id)) {
      setErrors([t('validation.duplicateCourse')])
      return
    }
    setErrors([])
    setSearchQuery('')
    setCourses((prev) => [...prev, draftFromCourseSummary(course, locale)])
    setFocusedCourseNumber(course.courseNumber)
  }

  const addMaybeCourse = (course: CourseSummary) => {
    if (!course.id) return
    if (isCourseInPlanner(course.id)) {
      setErrors([t('validation.duplicateCourse')])
      return
    }
    setErrors([])
    setSearchQuery('')
    setPlannerState((prev) =>
      addMaybeCourseToSnapshot(prev, draftFromCourseSummary(course, locale)),
    )
    setFocusedCourseNumber(course.courseNumber)
  }

  const removeCourse = (courseId: string) => {
    const removed = courses.find((course) => course.courseId === courseId)
    setCourses((prev) => prev.filter((course) => course.courseId !== courseId))
    if (removed?.courseNumber === focusedCourseNumber) {
      setFocusedCourseNumber(null)
    }
  }

  const removeMaybeCourse = (courseId: string) => {
    const removed = maybeCourses.find((course) => course.courseId === courseId)
    setPlannerState((prev) => removeMaybeCourseFromSnapshot(prev, courseId))
    if (removed?.courseNumber === focusedCourseNumber) {
      setFocusedCourseNumber(null)
    }
  }

  const moveSelectedToMaybe = (courseId: string) => {
    setPlannerState((prev) => moveSelectedToMaybeSnapshot(prev, courseId))
    const moved = courses.find((item) => item.courseId === courseId)
    if (moved) setFocusedCourseNumber(moved.courseNumber)
  }

  const moveMaybeToSelected = (courseId: string) => {
    setPlannerState((prev) => moveMaybeToSelectedSnapshot(prev, courseId))
    const moved = maybeCourses.find((item) => item.courseId === courseId)
    if (moved) setFocusedCourseNumber(moved.courseNumber)
  }

  const saveSelectedLessons = (
    courseNumber: string,
    selectedLessonEvents: SelectedLessonEvent[],
  ) => {
    const offering = clientPreviewQuery.data?.offeringsByCourse?.[courseNumber]
    const options = extractLessonOptions(offering, courseNumber)
    const groupSummary = selectedLessonEvents.length
      ? lessonSelectionSummary(options, selectedLessonEvents, t)
      : ''

    setCourses((prev) => {
      const nextCourses = prev.map((course) =>
        course.courseNumber === courseNumber
          ? { ...course, selectedLessonEvents, groupSummary: groupSummary || undefined }
          : course,
      )

      if (planId) {
        const course = nextCourses.find((item) => item.courseNumber === courseNumber)
        if (course && persistedCourseIds.has(course.courseId)) {
          if (lessonPatchTimerRef.current) {
            clearTimeout(lessonPatchTimerRef.current)
          }
          lessonPatchTimerRef.current = setTimeout(() => {
            lessonSelectionMutation.mutate({ courseNumber, selectedLessonEvents })
          }, 500)
        }
      }

      return nextCourses
    })
  }

  const saveMaybeLessons = (courseNumber: string, selectedLessonEvents: SelectedLessonEvent[]) => {
    const offering = clientPreviewQuery.data?.offeringsByCourse?.[courseNumber]
    const options = extractLessonOptions(offering, courseNumber)
    const groupSummary = selectedLessonEvents.length
      ? lessonSelectionSummary(options, selectedLessonEvents, t)
      : ''

    setPlannerState((prev) =>
      updateMaybeCourseLessons(
        prev,
        courseNumber,
        selectedLessonEvents,
        groupSummary || undefined,
      ),
    )

    if (planId) {
      const course = maybeCourses.find((item) => item.courseNumber === courseNumber)
      if (course) {
        if (maybeLessonPatchTimerRef.current) {
          clearTimeout(maybeLessonPatchTimerRef.current)
        }
        maybeLessonPatchTimerRef.current = setTimeout(() => {
          maybeLessonSelectionMutation.mutate({ courseNumber, selectedLessonEvents })
        }, 500)
      }
    }
  }

  const handleLessonGridClick = (eventId: string, courseNumber: string) => {
    const offering = clientPreviewQuery.data?.offeringsByCourse?.[courseNumber]
    const options = extractLessonOptions(offering, courseNumber)
    const option = options.find((item) => item.eventId === eventId)
    if (!option) return

    const selectedCourse = courses.find((item) => item.courseNumber === courseNumber)
    if (selectedCourse) {
      const nextEvents = toggleLessonSelection(
        selectedCourse.selectedLessonEvents ?? [],
        option,
        options,
      )
      saveSelectedLessons(courseNumber, nextEvents)
      setFocusedCourseNumber(courseNumber)
      return
    }

    const maybeCourse = maybeCourses.find((item) => item.courseNumber === courseNumber)
    if (!maybeCourse) return

    const nextEvents = toggleLessonSelection(maybeCourse.selectedLessonEvents ?? [], option, options)
    saveMaybeLessons(courseNumber, nextEvents)
    setFocusedCourseNumber(courseNumber)
  }

  const exportIcs = () => {
    const content = generatePlanIcs({
      planName: name.trim() || t('plans.newPlan'),
      schedule: displaySchedule ?? weeklySchedule,
      examSummary: displayExamSummary,
      customEvents,
      customEventsDirty,
    })
    const safeName = (name.trim() || 'semester-plan').replace(/[^\w-]+/g, '-').slice(0, 40)
    downloadIcs(content, `${safeName}.ics`)
  }

  const validateForm = (): boolean => {
    const nextFieldErrors: Record<string, string> = {}
    const nameResult = validatePlanName(name)
    if (!nameResult.ok) nextFieldErrors.name = t(nameResult.message)

    const semesterResult = validateSemesterCode(semesterCode)
    if (!semesterResult.ok) {
      nextFieldErrors.semesterCode = t(semesterResult.message)
    } else if (
      plannerSemesterOptions.length > 0 &&
      !plannerSemesterOptions.includes(semesterCode.trim())
    ) {
      nextFieldErrors.semesterCode = t('plans.plannerSemesterUnavailable')
    }

    if (!courses.length) nextFieldErrors.courses = t('validation.minOneCourse')

    setFieldErrors(nextFieldErrors)
    return Object.keys(nextFieldErrors).length === 0
  }

  const buildPayload = (includeSchedule: boolean) => {
    const plannedCourses: PlannedCourse[] = plannedCoursesForSave(courses)

    const semesterPayload: Record<string, unknown> = {
      semesterCode,
      goalCredits: totalCredits,
      plannedCourses,
      maybeCourses: plannedCoursesForSave(maybeCourses),
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

  const ensurePlanningProfileReady = async () => {
    await ensurePlanningProfile(fetchStudentProfileOrNull)
  }

  const buildExistingPlannedCoursesPayload = () => [
    ...courses.map((course) => ({
      courseId: course.courseId,
      courseNumber: course.courseNumber,
      courseTitle: course.courseTitle,
      credits: course.credits,
      isActive: course.isActive !== false,
      selectedLessonEvents: course.selectedLessonEvents,
    })),
    ...activeMaybeCourses.map((course) => ({
      courseId: course.courseId,
      courseNumber: course.courseNumber,
      courseTitle: course.courseTitle,
      credits: 0,
      isActive: true,
      selectedLessonEvents: course.selectedLessonEvents,
    })),
  ]

  const autoPickCoursesMutation = useMutation({
    mutationFn: async (maxCreditsValue: number) => {
      await ensurePlanningProfileReady()
      return plansApi.suggestCourses({
        semesterCode,
        maxCredits: maxCreditsValue,
        existingPlannedCourses: buildExistingPlannedCoursesPayload(),
      })
    },
    onSuccess: (data) => {
      let addedCount = 0
      setCourses((prev) => {
        const merged = mergeSuggestedCourses(prev, data.plannedCourses, {
          excludedCourseNumbers: maybeCourses.map((course) => course.courseNumber),
        })
        addedCount = merged.length - prev.length
        return merged
      })
      setAutoAssistError('')
      setErrors([])

      const explanation = data.explanation as CourseSuggestionExplanation
      const maxCredits = explanation.maxCredits ?? 0
      const semesterTotalCredits = explanation.semesterTotalCredits ?? explanation.totalRecommendedCredits ?? 0
      const reservedCredits = explanation.reservedCredits ?? 0
      const overBudget =
        addedCount === 0
        && maxCredits > 0
        && (reservedCredits > maxCredits || semesterTotalCredits > maxCredits)

      setAutoAssistStatusTone(overBudget ? 'warning' : 'success')
      setAutoAssistStatus(
        formatAutoPickStatus(addedCount, explanation, {
          success: t('planner.autoPickSuccess'),
          successPartial: t('planner.autoPickSuccessPartial'),
          empty: t('planner.autoPickEmpty'),
          noNewCourses: t('planner.autoPickNoNewCourses'),
          overBudget: t('planner.autoPickOverBudget'),
        }, formatCredits),
      )
    },
    onError: (err) => {
      setAutoAssistStatus('')
      setAutoAssistStatusTone('success')
      if (err instanceof PlanningProfileError) {
        setAutoAssistError(
          t(err.code === 'degree_required' ? 'progress.noDegree' : 'plans.profileRequired'),
        )
        return
      }
      setAutoAssistError(isAuthError(err) ? err.message : t('common.errorGeneric'))
    },
  })

  const persistPlanWithSchedule = async () => {
    if (!validateForm()) throw new Error('validation')
    await ensurePlanningProfileReady()
    const payload = buildPayload(true)
    if (planId) return plansApi.update(planId, payload)
    return plansApi.create(payload)
  }

  const persistPlanForInsights = async () => {
    const nameResult = validatePlanName(name)
    const semesterResult = validateSemesterCode(semesterCode)
    if (!nameResult.ok || !semesterResult.ok) throw new Error('validation')
    if (courses.length === 0 && maybeCourses.length === 0) throw new Error('validation')
    await ensurePlanningProfileReady()
    const payload = buildPayload(true)
    return plansApi.update(planId!, payload)
  }

  const maybeLessonSelectionMutation = useMutation({
    mutationFn: ({
      courseNumber,
      selectedLessonEvents,
    }: {
      courseNumber: string
      selectedLessonEvents: SelectedLessonEvent[]
    }) =>
      plansApi.patchMaybeLessonSelection(planId!, courseNumber, { selectedLessonEvents }),
    onSuccess: (data) => {
      const semester = data.semesterPlan.semesters[0]
      const savedMaybeCourses = draftCoursesFromPlanned(semester?.maybeCourses ?? [])
      setPlannerState((prev) => ({ ...prev, maybeCourses: savedMaybeCourses }))
      setPersistedMaybeSignature(buildMaybePersistSignature(savedMaybeCourses))
      queryClient.setQueryData(['plan', planId], data)
    },
    onError: handlePlannerMutationError,
  })

  const maybePersistMutation = useMutation({
    mutationFn: () =>
      plansApi.patchMaybeCourses(planId!, plannedCoursesForSave(maybeCourses) as Record<string, unknown>[]),
    onSuccess: (data) => {
      const semester = data.semesterPlan.semesters[0]
      const savedMaybeCourses = draftCoursesFromPlanned(semester?.maybeCourses ?? [])
      setPlannerState((prev) => ({ ...prev, maybeCourses: savedMaybeCourses }))
      setPersistedMaybeSignature(buildMaybePersistSignature(savedMaybeCourses))
      queryClient.setQueryData(['plan', planId], data)
    },
    onError: (err) => {
      if (err instanceof Error && err.message === 'validation') return
      handlePlannerMutationError(err)
    },
  })

  const saveMutation = useMutation({
    mutationFn: persistPlanWithSchedule,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
      syncFromSavedPlan(data.semesterPlan)
      if (!planId) {
        navigate(`/plans/${data.semesterPlan.id}/edit`, { replace: true })
      } else {
        queryClient.invalidateQueries({ queryKey: ['plan', planId] })
      }
    },
    onError: (err) => {
      if (err instanceof Error && err.message === 'validation') return
      setErrors([isAuthError(err) ? err.message : t('common.errorGeneric')])
    },
  })

  const insightsRefreshMutation = useMutation({
    mutationFn: persistPlanForInsights,
    onSuccess: (data) => {
      const plan = data.semesterPlan
      const semester = plan.semesters[0]
      setPlannerInsights(plan.plannerInsights)
      setWeeklySchedule(semester?.weeklySchedule)
      setPersistedCourseIds(
        new Set(
          (semester?.plannedCourses ?? [])
            .map((course) => course.courseId)
            .filter((courseId): courseId is string => Boolean(courseId)),
        ),
      )
      setPersistedSelectedSignature(selectedPersistSignatureRef.current)
      setPersistedMaybeSignature(maybePersistSignatureRef.current)
      setErrors([])
      queryClient.setQueryData(['plan', planId], data)
      queryClient.invalidateQueries({ queryKey: ['plans'] })
    },
    onError: (err) => {
      if (err instanceof Error && err.message === 'validation') return
      handlePlannerMutationError(err)
    },
  })

  useEffect(() => {
    if (skipAutoInsightsRef.current) return
    if (!planId) return
    if (selectedPersistSignature === persistedSelectedSignature) return
    if (courses.length === 0 && maybeCourses.length === 0) {
      setPlannerInsights(undefined)
      setWeeklySchedule(undefined)
      setPersistedSelectedSignature(selectedPersistSignature)
      setPersistedMaybeSignature(maybePersistSignature)
      setErrors([])
      return
    }

    const timer = setTimeout(() => {
      insightsRefreshMutation.mutate()
    }, 400)

    return () => clearTimeout(timer)
  }, [
    selectedPersistSignature,
    persistedSelectedSignature,
    maybePersistSignature,
    planId,
    courses.length,
    maybeCourses.length,
  ])

  useEffect(() => {
    if (skipAutoInsightsRef.current) return
    if (!planId) return
    if (maybePersistSignature === persistedMaybeSignature) return
    if (selectedPersistSignature !== persistedSelectedSignature) return

    const timer = setTimeout(() => {
      maybePersistMutation.mutate()
    }, 400)

    return () => clearTimeout(timer)
  }, [
    maybePersistSignature,
    persistedMaybeSignature,
    selectedPersistSignature,
    persistedSelectedSignature,
    planId,
  ])

  const planChanges = useMemo(() => buildPlanChanges(plannerInsights), [plannerInsights])
  const missingLessonCount = useMemo(() => {
    const localMissing = activeCourses.filter(
      (course) => !hasLessonSelection(course.selectedLessonEvents, course.selectedGroups),
    ).length
    const insightMissing =
      plannerInsights?.lessonSelectionWarnings?.filter((w) => w.type === 'no_lesson_selected').length ?? 0
    return Math.max(localMissing, insightMissing)
  }, [activeCourses, plannerInsights])

  const gridEmptyMessage = useMemo(() => {
    if (!activeCourses.length && !activeMaybeCourses.length) return t('planner.scheduleEmptyHint')
    if (activeCourses.length && missingLessonCount > 0) return t('planner.gridChooseLessonsHint')
    if (clientPreviewQuery.isLoading) return undefined
    return t('plans.scheduleEmpty')
  }, [
    activeCourses.length,
    activeMaybeCourses.length,
    missingLessonCount,
    clientPreviewQuery.isLoading,
    t,
  ])

  const showScheduleGrid =
    semesterSelected && (activeCourses.length > 0 || activeMaybeCourses.length > 0)

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
    if (filters.hideSelected) {
      items = filterSearchItemsForPlanner(items, { courses, maybeCourses, customEvents }, true)
    }
    if (filters.slotType) {
      items = items.filter((course) =>
        slotTypeMatches(course.semesterOfferingSummary?.slotTypes, filters.slotType),
      )
    }
    const includeList = filters.includeOnly
      .split(/[,\s]+/)
      .map((value) => value.trim())
      .filter(Boolean)
    if (includeList.length) {
      items = items.filter((course) => includeList.includes(course.courseNumber))
    }
    const excludeList = filters.exclude
      .split(/[,\s]+/)
      .map((value) => value.trim())
      .filter(Boolean)
    if (excludeList.length) {
      items = items.filter((course) => !excludeList.includes(course.courseNumber))
    }
    return items
  }, [searchResultsQuery.data?.items, filters, courses, maybeCourses])

  const scheduleGridEvents = useMemo(() => {
    if (!clientPreviewQuery.data?.offeringsByCourse) return []
    const toClientCourse = (course: DraftCourse) => ({
      courseNumber: course.courseNumber,
      courseTitle: course.courseTitle,
      isActive: course.isActive,
      selectedGroups: course.selectedGroups,
      selectedLessonEvents: course.selectedLessonEvents,
    })
    const offeringsByCourse: Record<string, (typeof clientPreviewQuery.data)['offeringsByCourse'][string]> = {}
    for (const course of previewCourses) {
      const offering = clientPreviewQuery.data!.offeringsByCourse[course.courseNumber]
      if (offering) {
        offeringsByCourse[course.courseNumber] = offering
      }
    }
    return buildScheduleGridEvents({
      courses: activeCourses.map(toClientCourse),
      maybeCourses: activeMaybeCourses.map(toClientCourse),
      offeringsByCourse,
      hoveredLessonEventId,
      customEvents,
    })
  }, [
    previewCourses,
    activeCourses,
    activeMaybeCourses,
    clientPreviewQuery.data?.offeringsByCourse,
    hoveredLessonEventId,
    customEvents,
  ])

  const selectedCourseNumbers = useMemo(
    () => new Set(courses.map((course) => course.courseNumber)),
    [courses],
  )

  const maybeCourseNumbers = useMemo(
    () => new Set(maybeCourses.map((course) => course.courseNumber)),
    [maybeCourses],
  )

  if (isEdit && planQuery.isLoading && !planQuery.data) {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24">
        <Spinner />
        <p className="text-sm text-[var(--color-text-muted)]">{t('common.loading')}</p>
      </div>
    )
  }

  const handleCourseHover = (courseNumber: string | null) => {
    setConflictHighlightNumbers(null)
    setHighlightedCourseNumber(courseNumber)
  }

  const handleLessonHover = (eventId: string | null, courseNumber: string | null) => {
    setConflictHighlightNumbers(null)
    setHoveredLessonEventId(eventId)
    setHighlightedCourseNumber(courseNumber)
  }

  const handleConflictHover = (courseNumbers: string[] | null) => {
    setHighlightedCourseNumber(null)
    setConflictHighlightNumbers(courseNumbers ? new Set(courseNumbers) : null)
  }

  return (
    <div className="space-y-3 planner-workspace print:space-y-2">
      <PlannerTopBar
        semesterCode={semesterCode}
        onSemesterChange={setSemesterCode}
        semesterOptions={plannerSemesterOptions}
        semesterOptionsLoading={plannerSemestersQuery.isLoading}
        semesterError={fieldErrors.semesterCode}
        planName={name}
        onPlanNameChange={(value) => {
          setNameTouched(true)
          setName(value)
        }}
        planNameError={fieldErrors.name}
        canUndo={canUndo}
        canRedo={canRedo}
        onUndo={undoPlanner}
        onRedo={redoPlanner}
        onExportIcs={activeCourses.length ? exportIcs : undefined}
        exportDisabled={!displaySchedule?.weekView?.length}
        onSave={() => saveMutation.mutate()}
        saving={saveMutation.isPending}
        onShowChanges={() => setShowChangesDialog(true)}
        changesCount={planChanges.length}
      />

      <PlannerSummaryBar
        activeCount={activeCourses.length}
        totalCount={courses.length}
        activeCredits={totalCredits}
        conflictCount={conflictCount}
        examCount={examCount}
        maxCredits={maxCreditsPref}
        missingLessonCount={missingLessonCount}
        changesCount={planChanges.length}
      />

      <PlannerAutoAssistPanel
        semesterCode={semesterCode}
        semesterSelected={semesterSelected}
        defaultMaxCredits={maxCreditsPref}
        pickingCourses={autoPickCoursesMutation.isPending}
        statusMessage={autoAssistStatus}
        statusTone={autoAssistStatusTone}
        errorMessage={autoAssistError}
        onAutoPickCourses={(maxCreditsValue) => autoPickCoursesMutation.mutate(maxCreditsValue)}
      />

      {errors.length ? (
        <div className="rounded-xl border border-[var(--color-danger)]/30 bg-[var(--color-danger)]/5 px-4 py-3 text-sm text-[var(--color-danger)] print:hidden">
          {errors.join(' · ')}
        </div>
      ) : null}

      <PlannerCourseSearch
        locale={locale}
        searchQuery={searchQuery}
        onSearchQueryChange={setSearchQuery}
        semesterSelected={semesterSelected}
        searchMinLength={searchMinLength}
        debouncedSearch={debouncedSearch}
        loading={searchResultsQuery.isLoading}
        error={searchResultsQuery.isError}
        items={searchItems}
        selectedCourseNumbers={selectedCourseNumbers}
        maybeCourseNumbers={maybeCourseNumbers}
        onAdd={addCourse}
        onAddMaybe={addMaybeCourse}
        onInfo={setDetailCourseNumber}
        filters={filters}
        onFiltersChange={(patch) => setFilters((current) => ({ ...current, ...patch }))}
        filtersExpanded={filtersExpanded}
        onToggleFilters={() => setFiltersExpanded((value) => !value)}
      />

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_240px] xl:items-start">
        <div className="order-2 min-w-0 space-y-3 xl:order-1">
          <Card className="print:border-0 print:shadow-none">
            <div className="mb-2 print:hidden">
              <h3 className="text-base font-semibold">{t('plans.weeklySchedule')}</h3>
              <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{t('planner.liveScheduleHint')}</p>
            </div>

            {!semesterSelected ? (
              <p className="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-16 text-center text-sm text-[var(--color-text-muted)]">
                {t('planner.selectSemesterFirst')}
              </p>
            ) : !showScheduleGrid ? (
              <p className="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-16 text-center text-sm text-[var(--color-text-muted)]">
                {t('planner.scheduleEmptyHint')}
              </p>
            ) : clientPreviewQuery.isLoading && !displaySchedule?.weekView?.length ? (
              <div className="flex justify-center py-16">
                <Spinner />
              </div>
            ) : (
              <>
                <WeeklyScheduleGrid
                  schedule={displaySchedule}
                  lessonEvents={scheduleGridEvents}
                  highlightedCourseNumber={highlightedCourseNumber}
                  highlightedCourseNumbers={conflictHighlightNumbers ?? undefined}
                  conflictCourseNumbers={conflictNumbers}
                  emptyMessage={gridEmptyMessage}
                  showEmptyGrid={activeCourses.length > 0 || activeMaybeCourses.length > 0}
                  onLessonHover={handleLessonHover}
                  onLessonClick={handleLessonGridClick}
                  onConflictHover={handleConflictHover}
                />
                {insightsRefreshMutation.isPending ? (
                  <p className="mt-3 flex items-center gap-2 text-xs text-[var(--color-text-muted)] print:hidden">
                    <Spinner />
                    {t('planner.updatingInsights')}
                  </p>
                ) : null}
                {!planId && activeCourses.length ? (
                  <p className="mt-3 text-xs text-[var(--color-text-muted)] print:hidden">
                    {t('planner.saveForPrereqChecks')}
                  </p>
                ) : null}
              </>
            )}
          </Card>

          {activeCourses.length ? (
            <ExamSummaryPanel
              summary={displayExamSummary}
              highlightedCourseNumber={highlightedCourseNumber}
              highlightedCourseNumbers={conflictHighlightNumbers ?? undefined}
              onExamHover={handleCourseHover}
              className="print:hidden"
            />
          ) : null}

          {activeCourses.length ? (
            <CustomEventsPanel
              events={customEvents}
              onChange={(events) => {
                setCustomEvents(events)
                setCustomEventsDirty(true)
              }}
              className="print:hidden"
            />
          ) : null}

          {planId ? (
            <SharePlanPanel
              embedded
              planId={planId}
              plan={{
                shareEnabled: planQuery.data?.semesterPlan.shareEnabled,
                shareToken: planQuery.data?.semesterPlan.shareToken,
                status: planQuery.data?.semesterPlan.status,
              }}
            />
          ) : null}

          {customEventsDirty ? (
            <p className="text-xs text-[var(--color-warning)] print:hidden">
              {t('planner.customEventsRebuildHint')}
            </p>
          ) : null}
        </div>

        <div className="order-1 flex min-h-0 flex-col gap-3 xl:order-2 xl:sticky xl:top-4 xl:max-h-[calc(100vh-10rem)] xl:overflow-hidden">
          <SelectedCoursesPanel
            className="xl:min-h-0 xl:flex-1 xl:overflow-hidden"
            courseCount={courses.length}
            creditsWarning={plannerInsights?.creditsWarning?.message}
            coursesError={fieldErrors.courses}
          >
            {courses.map((course) => (
              <SelectedCourseListItem
                key={course.courseId}
                course={course}
                variant="selected"
                focused={focusedCourseNumber === course.courseNumber}
                highlighted={
                  highlightedCourseNumber === course.courseNumber ||
                  Boolean(conflictHighlightNumbers?.has(course.courseNumber))
                }
                onHover={handleCourseHover}
                onFocus={() => setFocusedCourseNumber(course.courseNumber)}
                onMoveToOtherList={() => moveSelectedToMaybe(course.courseId)}
                onRemove={() => removeCourse(course.courseId)}
              />
            ))}
          </SelectedCoursesPanel>

          <MaybeCoursesPanel courseCount={maybeCourses.length} className="xl:shrink-0">
            {maybeCourses.map((course) => (
              <SelectedCourseListItem
                key={course.courseId}
                course={course}
                variant="maybe"
                focused={focusedCourseNumber === course.courseNumber}
                highlighted={
                  highlightedCourseNumber === course.courseNumber ||
                  Boolean(conflictHighlightNumbers?.has(course.courseNumber))
                }
                onHover={handleCourseHover}
                onFocus={() => setFocusedCourseNumber(course.courseNumber)}
                onMoveToOtherList={() => moveMaybeToSelected(course.courseId)}
                onRemove={() => removeMaybeCourse(course.courseId)}
              />
            ))}
          </MaybeCoursesPanel>
        </div>
      </div>

      <CourseDetailModal
        courseNumber={detailCourseNumber}
        academicYear={parsedSemester?.academicYear}
        semesterCode={parsedSemester?.semesterCode}
        onClose={() => setDetailCourseNumber(null)}
      />

      {showChangesDialog ? (
        <ChangesDialog changes={planChanges} onClose={() => setShowChangesDialog(false)} />
      ) : null}
    </div>
  )
}
