import type { ExamSummary, PlannedCourse, SelectedLessonEvent } from '../types/api'
import type { DraftCourse } from '../types/planner'
import { courseNumberKeys } from './courseNumbers'

function addNumberKeys(target: Set<string>, value: string) {
  for (const key of courseNumberKeys(value)) {
    target.add(key)
  }
}

function numberSetMatches(set: Set<string>, value: string): boolean {
  return courseNumberKeys(value).some((key) => set.has(key))
}

export function mergeSuggestedCourses(
  current: DraftCourse[],
  suggested: PlannedCourse[],
  options?: { excludedCourseNumbers?: Iterable<string> },
): DraftCourse[] {
  const existingIds = new Set(current.map((course) => course.courseId))
  const existingNumbers = new Set<string>()
  for (const course of current) {
    addNumberKeys(existingNumbers, course.courseNumber)
  }
  const excludedNumbers = new Set<string>()
  for (const number of options?.excludedCourseNumbers ?? []) {
    addNumberKeys(excludedNumbers, number)
  }
  const merged = [...current]

  for (const course of suggested) {
    if (!course.courseId) continue
    const courseNumber = course.courseNumber ?? ''
    if (
      existingIds.has(course.courseId)
      || numberSetMatches(existingNumbers, courseNumber)
      || numberSetMatches(excludedNumbers, courseNumber)
    ) {
      continue
    }
    merged.push({
      courseId: course.courseId,
      courseNumber: course.courseNumber ?? '',
      courseTitle: course.courseTitle ?? '',
      credits: course.credits ?? 0,
      isActive: course.isActive !== false,
      selectedLessonEvents: course.selectedLessonEvents,
    })
    existingIds.add(course.courseId)
    addNumberKeys(existingNumbers, courseNumber)
  }

  return merged
}

export function applyScheduleSelections(
  courses: DraftCourse[],
  selections: Array<{ courseNumber: string; selectedLessonEvents: SelectedLessonEvent[] }>,
): DraftCourse[] {
  const byNumber = new Map<string, SelectedLessonEvent[]>()
  for (const selection of selections) {
    for (const key of courseNumberKeys(selection.courseNumber)) {
      byNumber.set(key, selection.selectedLessonEvents)
    }
  }

  return courses.map((course) => {
    const keys = courseNumberKeys(course.courseNumber)
    const selectedLessonEvents = keys
      .map((key) => byNumber.get(key))
      .find((events) => events != null)
    if (!selectedLessonEvents) return course
    return { ...course, selectedLessonEvents }
  })
}

export type CourseSuggestionExplanation = {
  summary?: string
  selectedCount?: number
  totalRecommendedCredits?: number
  semesterTotalCredits?: number
  reservedCredits?: number
  maxCredits?: number
  partialPlan?: boolean
  emptyPlan?: boolean
  skippedDueToWorkload?: Array<{ courseNumber?: string; courseTitle?: string }>
  skippedDueToConflicts?: Array<{ courseNumber?: string; courseTitle?: string; reason?: string }>
  skippedDueToUnavailable?: Array<{ courseNumber?: string; courseTitle?: string; reason?: string }>
}

type AutoPickStatusLabels = {
  success: string
  successPartial: string
  successPartialMerge: string
  empty: string
  emptyWorkload: string
  emptyConflicts: string
  emptyUnavailable: string
  emptyMixed: string
  emptyReasonWorkload: string
  emptyReasonConflicts: string
  emptyReasonUnavailable: string
  noNewCourses: string
  mergeFiltered: string
  overBudget: string
}

type EmptySkipReason = 'workload' | 'conflicts' | 'unavailable'

function collectEmptySkipReasons(explanation: CourseSuggestionExplanation): EmptySkipReason[] {
  const reasons: EmptySkipReason[] = []
  if ((explanation.skippedDueToWorkload?.length ?? 0) > 0) reasons.push('workload')
  if ((explanation.skippedDueToConflicts?.length ?? 0) > 0) reasons.push('conflicts')
  if ((explanation.skippedDueToUnavailable?.length ?? 0) > 0) reasons.push('unavailable')
  return reasons
}

function buildEmptySkipReasonDetails(
  reasons: EmptySkipReason[],
  labels: Pick<
    AutoPickStatusLabels,
    'emptyReasonWorkload' | 'emptyReasonConflicts' | 'emptyReasonUnavailable'
  >,
  formatCredits: (value: number) => string,
  maxCredits: number,
): string {
  const parts: string[] = []
  if (reasons.includes('workload')) {
    parts.push(labels.emptyReasonWorkload.replace('{max}', formatCredits(maxCredits)))
  }
  if (reasons.includes('conflicts')) {
    parts.push(labels.emptyReasonConflicts)
  }
  if (reasons.includes('unavailable')) {
    parts.push(labels.emptyReasonUnavailable)
  }
  return parts.join(', ')
}

export function formatAutoPickStatus(
  addedCount: number,
  explanation: CourseSuggestionExplanation,
  labels: AutoPickStatusLabels,
  formatCredits: (value: number) => string,
): string {
  const selectedCount = explanation.selectedCount ?? 0
  const newCredits = explanation.totalRecommendedCredits ?? 0
  const semesterTotalCredits = explanation.semesterTotalCredits ?? newCredits
  const reservedCredits = explanation.reservedCredits ?? 0
  const maxCredits = explanation.maxCredits ?? 0
  const filteredCount = Math.max(0, selectedCount - addedCount)
  const isPartial =
    explanation.partialPlan ??
    (selectedCount > 0 && maxCredits > 0 && semesterTotalCredits < maxCredits)

  if (addedCount > 0) {
    if (filteredCount > 0) {
      return labels.successPartialMerge
        .replace('{added}', String(addedCount))
        .replace('{filtered}', String(filteredCount))
        .replace('{credits}', formatCredits(isPartial ? semesterTotalCredits : newCredits))
        .replace('{max}', formatCredits(maxCredits))
    }

    const template = isPartial ? labels.successPartial : labels.success
    const creditsForMessage = isPartial ? semesterTotalCredits : newCredits
    return template
      .replace('{count}', String(addedCount))
      .replace('{credits}', formatCredits(creditsForMessage))
      .replace('{max}', formatCredits(maxCredits))
  }

  if (
    maxCredits > 0
    && (reservedCredits > maxCredits || semesterTotalCredits > maxCredits)
  ) {
    return labels.overBudget
      .replace('{credits}', formatCredits(semesterTotalCredits))
      .replace('{max}', formatCredits(maxCredits))
  }

  if (addedCount === 0 && selectedCount > 0) {
    return labels.mergeFiltered.replace('{count}', String(selectedCount))
  }

  if (selectedCount > 0 || reservedCredits > 0) {
    return labels.noNewCourses
  }

  const skipReasons = collectEmptySkipReasons(explanation)
  if (skipReasons.length > 1) {
    return labels.emptyMixed.replace(
      '{reasons}',
      buildEmptySkipReasonDetails(skipReasons, labels, formatCredits, maxCredits),
    )
  }
  if (skipReasons.length === 1) {
    const skipReason = skipReasons[0]
    if (skipReason === 'workload') {
      return labels.emptyWorkload.replace('{max}', formatCredits(maxCredits))
    }
    if (skipReason === 'conflicts') {
      return labels.emptyConflicts
    }
    if (skipReason === 'unavailable') {
      return labels.emptyUnavailable
    }
  }

  return labels.empty
}

export type ScheduleSuggestionResult = {
  selections: Array<{ courseNumber: string; selectedLessonEvents: SelectedLessonEvent[] }>
  skippedCourses: Array<{ courseNumber?: string; reason?: string }>
  examSummary?: ExamSummary
}
