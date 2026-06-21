/** Pure helpers for maybe-course list logic (selected ↔ maybe moves, search, save boundaries). */

import type { PlannedCourse, SelectedLessonEvent } from '../types/api'
import type { DraftCourse, PlannerSnapshot } from '../types/planner'

export function isCourseInPlannerLists(
  courses: DraftCourse[],
  maybeCourses: DraftCourse[],
  courseId: string,
): boolean {
  return (
    courses.some((course) => course.courseId === courseId) ||
    maybeCourses.some((course) => course.courseId === courseId)
  )
}

export function activeDraftCourses(courses: DraftCourse[]): DraftCourse[] {
  return courses.filter((course) => course.isActive !== false)
}

export function previewCourseNumbers(selected: DraftCourse[], maybe: DraftCourse[]): string[] {
  return [...activeDraftCourses(selected), ...activeDraftCourses(maybe)].map(
    (course) => course.courseNumber,
  )
}

export function moveSelectedToMaybeSnapshot(
  snapshot: PlannerSnapshot,
  courseId: string,
): PlannerSnapshot {
  const course = snapshot.courses.find((item) => item.courseId === courseId)
  if (!course) return snapshot
  return {
    ...snapshot,
    courses: snapshot.courses.filter((item) => item.courseId !== courseId),
    maybeCourses: [...snapshot.maybeCourses, course],
  }
}

export function moveMaybeToSelectedSnapshot(
  snapshot: PlannerSnapshot,
  courseId: string,
): PlannerSnapshot {
  const course = snapshot.maybeCourses.find((item) => item.courseId === courseId)
  if (!course) return snapshot
  return {
    ...snapshot,
    maybeCourses: snapshot.maybeCourses.filter((item) => item.courseId !== courseId),
    courses: [...snapshot.courses, course],
  }
}

export function addMaybeCourseToSnapshot(
  snapshot: PlannerSnapshot,
  course: DraftCourse,
): PlannerSnapshot {
  if (isCourseInPlannerLists(snapshot.courses, snapshot.maybeCourses, course.courseId)) {
    return snapshot
  }
  return {
    ...snapshot,
    maybeCourses: [...snapshot.maybeCourses, course],
  }
}

export function removeMaybeCourseFromSnapshot(
  snapshot: PlannerSnapshot,
  courseId: string,
): PlannerSnapshot {
  return {
    ...snapshot,
    maybeCourses: snapshot.maybeCourses.filter((course) => course.courseId !== courseId),
  }
}

export function updateMaybeCourseLessons(
  snapshot: PlannerSnapshot,
  courseNumber: string,
  selectedLessonEvents: SelectedLessonEvent[],
  groupSummary?: string,
): PlannerSnapshot {
  return {
    ...snapshot,
    maybeCourses: snapshot.maybeCourses.map((course) =>
      course.courseNumber === courseNumber
        ? { ...course, selectedLessonEvents, groupSummary: groupSummary || undefined }
        : course,
    ),
  }
}

export function filterSearchItemsForPlanner<T extends { id?: string | null }>(
  items: T[],
  snapshot: PlannerSnapshot,
  hideSelected: boolean,
): T[] {
  if (!hideSelected) return items
  return items.filter(
    (item) =>
      item.id &&
      !snapshot.courses.some((course) => course.courseId === item.id) &&
      !snapshot.maybeCourses.some((course) => course.courseId === item.id),
  )
}

export function draftCoursesFromPlanned(planned: PlannedCourse[]): DraftCourse[] {
  return planned.map((course) => ({
    courseId: course.courseId,
    courseNumber: course.courseNumber ?? '',
    courseTitle: course.courseTitle ?? '',
    credits: course.credits ?? 0,
    isActive: course.isActive !== false,
    selectedGroups: course.selectedGroups,
    selectedLessonEvents: course.selectedLessonEvents,
    notes: course.notes,
  }))
}

export function plannedCoursesForSave(courses: DraftCourse[]): PlannedCourse[] {
  return courses.map((course) => ({
    courseId: course.courseId,
    category: 'manual',
    isActive: course.isActive,
    selectedGroups: course.selectedGroups,
    selectedLessonEvents: course.selectedLessonEvents,
    notes: course.notes,
  }))
}

export function savePayloadCourseIds(payload: {
  semesters?: Array<{ plannedCourses?: Array<{ courseId?: string }> }>
}): string[] {
  return (payload.semesters?.[0]?.plannedCourses ?? [])
    .map((course) => course.courseId)
    .filter((courseId): courseId is string => Boolean(courseId))
}

export function savePayloadMaybeCourseIds(payload: {
  semesters?: Array<{ maybeCourses?: Array<{ courseId?: string }> }>
}): string[] {
  return (payload.semesters?.[0]?.maybeCourses ?? [])
    .map((course) => course.courseId)
    .filter((courseId): courseId is string => Boolean(courseId))
}

export function buildSelectedPersistSignature(courses: DraftCourse[]): string {
  return JSON.stringify(
    courses.map((course) => ({
      id: course.courseId,
      active: course.isActive !== false,
      events: course.selectedLessonEvents ?? [],
    })),
  )
}

export function buildMaybePersistSignature(maybeCourses: DraftCourse[]): string {
  return JSON.stringify(
    maybeCourses.map((course) => ({
      id: course.courseId,
      active: course.isActive !== false,
      events: course.selectedLessonEvents ?? [],
    })),
  )
}

export function buildPlannerPersistSignature(
  courses: DraftCourse[],
  maybeCourses: DraftCourse[],
): string {
  return JSON.stringify({
    selected: buildSelectedPersistSignature(courses),
    maybe: buildMaybePersistSignature(maybeCourses),
  })
}

export function hydratePlannerFromServer(
  snapshot: PlannerSnapshot,
  serverCourses: DraftCourse[],
  serverMaybeCourses?: DraftCourse[],
): PlannerSnapshot {
  return {
    courses: serverCourses,
    maybeCourses: serverMaybeCourses ?? snapshot.maybeCourses,
    customEvents: snapshot.customEvents,
  }
}
