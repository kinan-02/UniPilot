/** Client-side schedule preview from catalog offerings (CheeseFork-style live grid). */

import type { CourseOffering, CustomEvent, SelectedGroups, SelectedLessonEvent, WeeklySchedule } from '../types/api'
import {
  collectGridEvents,
  type GridEvent,
  parseTimeRange,
  slotsOverlap,
} from './planner'
import { filterGroupsByLessonSelection } from './lessonEvents'

export type ClientScheduleCourse = {
  courseNumber: string
  courseTitle: string
  isActive?: boolean
  selectedGroups?: SelectedGroups
  selectedLessonEvents?: SelectedLessonEvent[]
}

export type ScheduleConflict = {
  day: string
  timeRange: string
  courseNumbers: string[]
  reason: string
}

function normalizeGroup(group: Record<string, string>) {
  return {
    day: group.day || group.יום || '',
    timeRange: group.time || group.שעה || '',
    slotType: group.type || group.סוג || '',
  }
}

export function filterGroupsBySelection(
  scheduleGroups: Array<Record<string, string>> = [],
  selectedGroups?: SelectedGroups,
  selectedLessonEvents?: SelectedLessonEvent[],
  meta?: { courseNumber?: string; academicYear?: number; semesterCode?: number },
): Array<Record<string, string>> {
  return filterGroupsByLessonSelection(scheduleGroups, {
    selectedGroups,
    selectedLessonEvents,
    courseNumber: meta?.courseNumber,
    academicYear: meta?.academicYear,
    semesterCode: meta?.semesterCode,
  }) as Array<Record<string, string>>
}

export function eventsFromOffering(
  course: ClientScheduleCourse,
  offering?: CourseOffering,
): GridEvent[] {
  if (!offering?.scheduleGroups?.length) return []
  if (course.isActive === false) return []

  const groups = filterGroupsBySelection(
    offering.scheduleGroups as Array<Record<string, string>>,
    course.selectedGroups,
    course.selectedLessonEvents,
    {
      courseNumber: course.courseNumber,
      academicYear: offering.academicYear,
      semesterCode: offering.semesterCode,
    },
  )

  const events: GridEvent[] = []
  for (const group of groups) {
    const normalized = normalizeGroup(group)
    const parsed = parseTimeRange(normalized.timeRange.replace(/[–—]/g, '-'))
    if (!normalized.day || !parsed) continue
    events.push({
      day: normalized.day,
      timeRange: normalized.timeRange,
      slotType: normalized.slotType,
      courseNumber: course.courseNumber,
      courseTitle: course.courseTitle,
      startMinutes: parsed.start,
      endMinutes: parsed.end,
    })
  }
  return events
}

export function detectScheduleConflicts(events: GridEvent[]): ScheduleConflict[] {
  const conflicts: ScheduleConflict[] = []
  const seen = new Set<string>()

  for (let leftIndex = 0; leftIndex < events.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < events.length; rightIndex += 1) {
      const left = events[leftIndex]
      const right = events[rightIndex]
      if (left.courseNumber === right.courseNumber) continue
      if (
        !slotsOverlap(
          { day: left.day, start: left.startMinutes, end: left.endMinutes },
          { day: right.day, start: right.startMinutes, end: right.endMinutes },
        )
      ) {
        continue
      }

      const pairKey = [left.courseNumber, right.courseNumber, left.day, left.timeRange]
        .sort()
        .join('|')
      if (seen.has(pairKey)) continue
      seen.add(pairKey)

      conflicts.push({
        day: left.day,
        timeRange: left.timeRange,
        courseNumbers: [left.courseNumber!, right.courseNumber!].sort(),
        reason: 'Overlapping schedule slots',
      })
    }
  }

  return conflicts
}

export function buildClientWeeklySchedule(
  courseEvents: GridEvent[],
  customEvents: CustomEvent[] = [],
): WeeklySchedule {
  const conflicts = detectScheduleConflicts(courseEvents)
  const grouped = new Map<string, GridEvent[]>()

  for (const event of courseEvents) {
    const dayEvents = grouped.get(event.day) ?? []
    dayEvents.push(event)
    grouped.set(event.day, dayEvents)
  }

  const weekView = [...grouped.entries()].map(([day, slots]) => ({
    day,
    slots: slots.map((slot) => ({
      day: slot.day,
      timeRange: slot.timeRange,
      slotType: slot.slotType,
      courseNumber: slot.courseNumber,
      courseTitle: slot.courseTitle,
    })),
  }))

  return {
    status: conflicts.length ? 'conflicts' : courseEvents.length ? 'valid' : 'empty',
    summary:
      conflicts.length > 0
        ? `${courseEvents.length} events · ${conflicts.length} conflict(s)`
        : courseEvents.length > 0
          ? `${courseEvents.length} events · no conflicts`
          : 'No schedule events',
    conflicts,
    weekView,
    customEvents,
  }
}

export function mergeScheduleViews(
  clientSchedule: WeeklySchedule | undefined,
  serverSchedule: WeeklySchedule | undefined,
  preferServer: boolean,
  customEvents: CustomEvent[],
  customEventsDirty: boolean,
): { schedule?: WeeklySchedule; events: GridEvent[] } {
  const schedule = preferServer && serverSchedule?.weekView?.length ? serverSchedule : clientSchedule
  const events = collectGridEvents(schedule, customEvents, [], customEventsDirty)
  return { schedule, events }
}
