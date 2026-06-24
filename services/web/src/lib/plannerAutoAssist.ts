import type { ExamSummary, PlannedCourse, SelectedLessonEvent } from '../types/api'
import type { DraftCourse } from '../types/planner'

export function mergeSuggestedCourses(
  current: DraftCourse[],
  suggested: PlannedCourse[],
): DraftCourse[] {
  const existingIds = new Set(current.map((course) => course.courseId))
  const existingNumbers = new Set(current.map((course) => course.courseNumber))
  const merged = [...current]

  for (const course of suggested) {
    if (!course.courseId) continue
    if (existingIds.has(course.courseId) || existingNumbers.has(course.courseNumber ?? '')) {
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
}

export function formatAutoPickStatus(
  addedCount: number,
  explanation: CourseSuggestionExplanation,
  labels: AutoPickStatusLabels,
  formatCredits: (value: number) => string,
): string {
  const selectedCount = explanation.selectedCount ?? 0
  const totalCredits = explanation.totalRecommendedCredits ?? 0
  const maxCredits = explanation.maxCredits ?? 0
  const isPartial =
    explanation.partialPlan ??
    (selectedCount > 0 && maxCredits > 0 && totalCredits < maxCredits)

  if (addedCount > 0) {
    const template = isPartial ? labels.successPartial : labels.success
    return template
      .replace('{count}', String(addedCount))
      .replace('{credits}', formatCredits(totalCredits))
      .replace('{max}', formatCredits(maxCredits))
  }

  if (selectedCount > 0) {
    return labels.noNewCourses
  }

  return labels.empty
}

export type ScheduleSuggestionResult = {
  selections: Array<{ courseNumber: string; selectedLessonEvents: SelectedLessonEvent[] }>
  skippedCourses: Array<{ courseNumber?: string; reason?: string }>
  examSummary?: ExamSummary
}
