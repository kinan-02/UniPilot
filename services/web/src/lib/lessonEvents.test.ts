import { describe, expect, it } from 'vitest'
import {
  buildLessonEventId,
  extractLessonOptions,
  filterGroupsByLessonSelection,
  hasLessonSelection,
  lessonSelectionSummary,
} from './lessonEvents'

describe('lessonEvents', () => {
  const offering = {
    courseNumber: '02340114',
    academicYear: 2025,
    semesterCode: 201,
    scheduleGroups: [
      { day: 'Sunday', time: '08:30-10:30', type: 'lecture', group: '10' },
      { day: 'Monday', time: '10:30-11:30', type: 'tutorial', group: '11' },
    ],
  }

  it('builds stable event ids', () => {
    const id = buildLessonEventId({
      courseNumber: '02340114',
      academicYear: 2025,
      semesterCode: 201,
      lessonType: 'lecture',
      groupLabel: '10',
      day: 'Sunday',
      startTime: '08:30',
      endTime: '10:30',
    })
    expect(id).toContain('02340114-2025-201-lecture-10-sunday-0830-1030')
  })

  it('returns empty schedule groups when nothing is selected', () => {
    const filtered = filterGroupsByLessonSelection(offering.scheduleGroups, {})
    expect(filtered).toEqual([])
  })

  it('filters by selected lesson events', () => {
    const options = extractLessonOptions(offering)
    const filtered = filterGroupsByLessonSelection(offering.scheduleGroups, {
      selectedLessonEvents: [{ eventId: options[0].eventId, type: 'lecture', group: '10' }],
      courseNumber: offering.courseNumber,
      academicYear: offering.academicYear,
      semesterCode: offering.semesterCode,
    })
    expect(filtered).toHaveLength(1)
  })

  it('summarizes selected and missing lesson types', () => {
    const options = extractLessonOptions(offering)
    const summary = lessonSelectionSummary(options, [options[0]], (key) => key)
    expect(summary).toContain('Lecture')
    expect(summary).toContain('planner.lessonNotSelected')
  })

  it('detects whether any lesson is selected', () => {
    expect(hasLessonSelection([], { lecture: 0 })).toBe(true)
    expect(hasLessonSelection([], {})).toBe(false)
  })
})
