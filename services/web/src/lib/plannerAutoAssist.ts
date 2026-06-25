import type { ExamSummary, PlannedCourse, SelectedLessonEvent } from '../types/api'
import type { DraftCourse } from '../types/planner'

export function mergeSuggestedCourses(
  current: DraftCourse[],
  suggested: PlannedCourse[],
  options?: { excludedCourseNumbers?: Iterable<string> },
): DraftCourse[] {
  const existingIds = new Set(current.map((course) => course.courseId))
  const existingNumbers = new Set(current.map((course) => course.courseNumber))
  const excludedNumbers = new Set(options?.excludedCourseNumbers ?? [])
  const merged = [...current]

  for (const course of suggested) {
    if (!course.courseId) continue
    const courseNumber = course.courseNumber ?? ''
    if (
      existingIds.has(course.courseId)
      || existingNumbers.has(courseNumber)
      || excludedNumbers.has(courseNumber)
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
    existingNumbers.add(course.courseNumber ?? '')
  }

  return merged
}

export function applyScheduleSelections(
  courses: DraftCourse[],
  selections: Array<{ courseNumber: string; selectedLessonEvents: SelectedLessonEvent[] }>,
): DraftCourse[] {
  const byNumber = new Map(
    selections.map((selection) => [selection.courseNumber, selection.selectedLessonEvents]),
  )

  return courses.map((course) => {
    const selectedLessonEvents = byNumber.get(course.courseNumber)
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
}

type AutoPickStatusLabels = {
  success: string
  successPartial: string
  empty: string
  noNewCourses: string
  overBudget: string
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
  const isPartial =
    explanation.partialPlan ??
    (selectedCount > 0 && maxCredits > 0 && semesterTotalCredits < maxCredits)

  if (addedCount > 0) {
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

  if (selectedCount > 0 || reservedCredits > 0) {
    return labels.noNewCourses
  }

  return labels.empty
}

export type ScheduleSuggestionResult = {
  selections: Array<{ courseNumber: string; selectedLessonEvents: SelectedLessonEvent[] }>
  skippedCourses: Array<{ courseNumber?: string; reason?: string }>
  examSummary?: ExamSummary
}
