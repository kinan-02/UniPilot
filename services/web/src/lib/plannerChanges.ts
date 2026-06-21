import type { PlannerInsights } from '../types/api'
import type { PlanChangeItem } from '../types/planner'

/** Build human-readable change/stale warnings from planner insights. */
export function buildPlanChanges(insights?: PlannerInsights): PlanChangeItem[] {
  if (!insights) return []
  const items: PlanChangeItem[] = []

  for (const warning of insights.staleCourseWarnings ?? []) {
    items.push({
      id: `stale-${warning.courseNumber}`,
      courseNumber: warning.courseNumber,
      type: 'stale_offering',
      message: warning.message ?? 'Course offering unavailable for this semester',
    })
  }

  for (const warning of insights.lessonSelectionWarnings ?? []) {
    items.push({
      id: `lesson-${warning.courseNumber}-${warning.type}-${warning.eventId ?? 'none'}`,
      courseNumber: warning.courseNumber,
      type: warning.type ?? 'lesson_warning',
      message: warning.message ?? 'Lesson selection issue',
    })
  }

  for (const warning of insights.courseWarnings ?? []) {
    if (warning.status === 'none' || warning.status === 'satisfied') continue
    items.push({
      id: `prereq-${warning.courseId ?? warning.courseNumber}`,
      courseNumber: warning.courseNumber,
      type: warning.status ?? 'prerequisite',
      message: warning.message ?? 'Prerequisite verification needed',
    })
  }

  for (const warning of insights.examSummary?.warnings ?? []) {
    items.push({
      id: `exam-${warning.date ?? warning.type}-${(warning.courseNumbers ?? []).join('-')}`,
      type: warning.type ?? 'exam_warning',
      message: warning.message ?? 'Exam schedule warning',
    })
  }

  return items
}
