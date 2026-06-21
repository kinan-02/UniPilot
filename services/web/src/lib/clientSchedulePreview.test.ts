import { describe, expect, it } from 'vitest'
import {
  buildClientWeeklySchedule,
  detectScheduleConflicts,
  eventsFromOffering,
  filterGroupsBySelection,
} from './clientSchedulePreview'
import { extractLessonOptions } from './lessonEvents'
import type { GridEvent } from './planner'

describe('clientSchedulePreview', () => {
  const sampleGroups = [
    { day: 'Sunday', time: '10:30-12:30', type: 'lecture' },
    { day: 'Sunday', time: '12:30-14:30', type: 'tutorial' },
  ]

  it('builds separate events for lecture and tutorial when selected', () => {
    const offering = {
      courseNumber: '01040001',
      academicYear: 2025,
      semesterCode: 201,
      scheduleGroups: sampleGroups,
    }
    const options = extractLessonOptions(offering)
    const events = eventsFromOffering(
      {
        courseNumber: '01040001',
        courseTitle: 'Intro',
        selectedLessonEvents: options.map((option) => ({
          eventId: option.eventId,
          type: option.type,
          group: option.group ?? undefined,
        })),
      },
      offering,
    )
    expect(events).toHaveLength(2)
    expect(events[0].slotType).toBe('lecture')
  })

  it('returns no events when no lessons are selected', () => {
    const events = eventsFromOffering(
      { courseNumber: '01040001', courseTitle: 'Intro' },
      {
        courseNumber: '01040001',
        academicYear: 2025,
        semesterCode: 201,
        scheduleGroups: sampleGroups,
      },
    )
    expect(events).toHaveLength(0)
  })

  it('filters groups by selectedGroups indices (legacy)', () => {
    const filtered = filterGroupsBySelection(sampleGroups, {
      lecture: 0,
      tutorial: null,
      lab: null,
      project: null,
    })
    expect(filtered).toHaveLength(1)
    expect(filtered[0].type).toBe('lecture')
  })

  it('detects overlapping courses on the same day', () => {
    const events: GridEvent[] = [
      {
        day: 'Sunday',
        timeRange: '10:00-12:00',
        courseNumber: '01040001',
        courseTitle: 'A',
        startMinutes: 600,
        endMinutes: 720,
      },
      {
        day: 'Sunday',
        timeRange: '11:00-13:00',
        courseNumber: '01040002',
        courseTitle: 'B',
        startMinutes: 660,
        endMinutes: 780,
      },
    ]
    const conflicts = detectScheduleConflicts(events)
    expect(conflicts).toHaveLength(1)
    expect(conflicts[0].courseNumbers).toEqual(['01040001', '01040002'])
  })

  it('treats adjacent slots as non-conflicting', () => {
    const events: GridEvent[] = [
      {
        day: 'Sunday',
        timeRange: '10:00-12:00',
        courseNumber: '01040001',
        courseTitle: 'A',
        startMinutes: 600,
        endMinutes: 720,
      },
      {
        day: 'Sunday',
        timeRange: '12:00-14:00',
        courseNumber: '01040002',
        courseTitle: 'B',
        startMinutes: 720,
        endMinutes: 840,
      },
    ]
    expect(detectScheduleConflicts(events)).toHaveLength(0)
  })

  it('builds weekly schedule summary with conflict count', () => {
    const schedule = buildClientWeeklySchedule([
      {
        day: 'Monday',
        timeRange: '09:00-11:00',
        courseNumber: '01040001',
        courseTitle: 'A',
        startMinutes: 540,
        endMinutes: 660,
      },
      {
        day: 'Monday',
        timeRange: '10:00-12:00',
        courseNumber: '01040002',
        courseTitle: 'B',
        startMinutes: 600,
        endMinutes: 720,
      },
    ])
    expect(schedule.status).toBe('conflicts')
    expect(schedule.conflicts).toHaveLength(1)
  })
})
