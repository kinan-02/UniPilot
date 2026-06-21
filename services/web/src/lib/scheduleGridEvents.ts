/** CheeseFork-style grid layers: selected, available, preview, and custom blocks. */

import type { CourseOffering, CustomEvent } from '../types/api'
import type { ClientScheduleCourse } from './clientSchedulePreview'
import { extractLessonOptions, type LessonOption } from './lessonEvents'
import {
  eventsFromCustomBlocks,
  parseTimeRange,
  slotsOverlap,
  type GridEvent,
} from './planner'

export type ScheduleGridEventKind = 'selected' | 'available' | 'preview' | 'custom' | 'maybe' | 'maybe-available'

export type ScheduleGridEvent = GridEvent & {
  eventId?: string
  kind: ScheduleGridEventKind
  lessonType?: string
  group?: string | null
  previewConflict?: boolean
}

export function lessonOptionToGridEvent(
  option: LessonOption,
  course: ClientScheduleCourse,
  kind: ScheduleGridEventKind,
): ScheduleGridEvent | null {
  const parsed = parseTimeRange(option.timeRange.replace(/[–—]/g, '-'))
  if (!option.day || !parsed) return null
  return {
    eventId: option.eventId,
    day: option.day,
    timeRange: option.timeRange,
    slotType: option.slotTypeLabel,
    lessonType: option.type,
    group: option.group,
    courseNumber: course.courseNumber,
    courseTitle: course.courseTitle,
    startMinutes: parsed.start,
    endMinutes: parsed.end,
    kind,
  }
}

export function selectedGridEventsFromCourses(
  courses: ClientScheduleCourse[],
  offeringsByCourse: Record<string, CourseOffering | undefined>,
): GridEvent[] {
  const events: GridEvent[] = []
  for (const course of courses) {
    if (course.isActive === false) continue
    const options = extractLessonOptions(offeringsByCourse[course.courseNumber], course.courseNumber)
    const selectedIds = new Set((course.selectedLessonEvents ?? []).map((event) => event.eventId))
    for (const option of options) {
      if (!selectedIds.has(option.eventId)) continue
      const gridEvent = lessonOptionToGridEvent(option, course, 'selected')
      if (gridEvent) events.push(gridEvent)
    }
  }
  return events
}

export function wouldLessonConflict(
  selectedEvents: GridEvent[],
  candidate: ScheduleGridEvent,
): boolean {
  return selectedEvents.some(
    (event) =>
      event.courseNumber !== candidate.courseNumber &&
      slotsOverlap(
        { day: event.day, start: event.startMinutes, end: event.endMinutes },
        { day: candidate.day, start: candidate.startMinutes, end: candidate.endMinutes },
      ),
  )
}

type BuildScheduleGridEventsArgs = {
  courses: ClientScheduleCourse[]
  maybeCourses?: ClientScheduleCourse[]
  offeringsByCourse: Record<string, CourseOffering | undefined>
  hoveredLessonEventId?: string | null
  customEvents?: CustomEvent[]
}

function appendCourseGridEvents(
  events: ScheduleGridEvent[],
  course: ClientScheduleCourse,
  offering: CourseOffering | undefined,
  mode: 'selected' | 'maybe',
  selectedForConflicts: GridEvent[],
  hoveredLessonEventId: string | null,
) {
  const isInactive = course.isActive === false
  if (isInactive) return

  const options = extractLessonOptions(offering, course.courseNumber)
  const selectedIds = new Set((course.selectedLessonEvents ?? []).map((event) => event.eventId))
  const selectedTypes = new Set(
    options.filter((option) => selectedIds.has(option.eventId)).map((option) => option.type),
  )

  for (const option of options) {
    const isSelected = selectedIds.has(option.eventId)
    if (!isSelected && selectedTypes.has(option.type)) continue

    const isHovered = hoveredLessonEventId === option.eventId
    let kind: ScheduleGridEventKind
    if (mode === 'selected') {
      kind = isSelected ? 'selected' : isHovered ? 'preview' : 'available'
    } else {
      kind = isSelected ? 'maybe' : isHovered ? 'maybe' : 'maybe-available'
    }

    const gridEvent = lessonOptionToGridEvent(option, course, kind)
    if (!gridEvent) continue

    if (kind === 'preview' || kind === 'available' || kind === 'maybe-available') {
      gridEvent.previewConflict = wouldLessonConflict(selectedForConflicts, gridEvent)
    }

    events.push(gridEvent)
  }
}

export function buildScheduleGridEvents({
  courses,
  maybeCourses = [],
  offeringsByCourse,
  hoveredLessonEventId = null,
  customEvents = [],
}: BuildScheduleGridEventsArgs): ScheduleGridEvent[] {
  const events: ScheduleGridEvent[] = []
  const selectedForConflicts = [
    ...selectedGridEventsFromCourses(courses, offeringsByCourse),
    ...selectedGridEventsFromCourses(maybeCourses, offeringsByCourse),
  ]

  for (const course of courses) {
    appendCourseGridEvents(
      events,
      course,
      offeringsByCourse[course.courseNumber],
      'selected',
      selectedForConflicts,
      hoveredLessonEventId,
    )
  }

  for (const course of maybeCourses) {
    appendCourseGridEvents(
      events,
      course,
      offeringsByCourse[course.courseNumber],
      'maybe',
      selectedForConflicts,
      hoveredLessonEventId,
    )
  }

  for (const custom of eventsFromCustomBlocks(customEvents)) {
    events.push({ ...custom, kind: 'custom' })
  }

  return events
}
