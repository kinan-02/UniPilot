import type { MasScheduleCourse } from '../types/api'
import type { ScheduleGridEvent } from './scheduleGridEvents'
import { parseTimeRange } from './planner'

/** Convert MAS semester schedule courses into planner grid events. */
export function masCoursesToGridEvents(courses: MasScheduleCourse[]): ScheduleGridEvent[] {
  const events: ScheduleGridEvent[] = []

  for (const course of courses) {
    for (const slot of course.slots) {
      const parsed = parseTimeRange(slot.timeRange.replace(/[–—]/g, '-'))
      if (!parsed || !slot.day) continue
      events.push({
        day: slot.day,
        timeRange: slot.timeRange,
        slotType: slot.slotType,
        group: slot.group,
        courseNumber: course.courseId,
        courseTitle: course.title,
        startMinutes: parsed.start,
        endMinutes: parsed.end,
        kind: 'selected',
      })
    }
  }

  return events.sort((a, b) => a.startMinutes - b.startMinutes)
}
