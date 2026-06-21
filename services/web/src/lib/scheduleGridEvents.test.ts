import { describe, expect, it } from 'vitest'
import { extractLessonOptions, toggleLessonSelection } from './lessonEvents'
import {
  buildScheduleGridEvents,
  selectedGridEventsFromCourses,
  wouldLessonConflict,
} from './scheduleGridEvents'

describe('toggleLessonSelection', () => {
  const offering = {
    courseNumber: '02340114',
    academicYear: 2025,
    semesterCode: 201,
    scheduleGroups: [
      { day: 'Sunday', time: '08:30-10:30', type: 'lecture', group: '10' },
      { day: 'Monday', time: '10:30-11:30', type: 'lecture', group: '11' },
      { day: 'Tuesday', time: '12:30-13:30', type: 'tutorial', group: '20' },
    ],
  }

  it('selects and unselects a lesson event', () => {
    const options = extractLessonOptions(offering)
    const selected = toggleLessonSelection([], options[0], options)
    expect(selected).toHaveLength(1)
    expect(toggleLessonSelection(selected, options[0], options)).toHaveLength(0)
  })

  it('replaces another group of the same lesson type', () => {
    const options = extractLessonOptions(offering)
    const first = toggleLessonSelection([], options[0], options)
    const second = toggleLessonSelection(first, options[1], options)
    expect(second).toHaveLength(1)
    expect(second[0].eventId).toBe(options[1].eventId)
  })
})

describe('buildScheduleGridEvents', () => {
  const offering = {
    courseNumber: '02340114',
    academicYear: 2025,
    semesterCode: 201,
    scheduleGroups: [
      { day: 'Sunday', time: '08:30-10:30', type: 'lecture', group: '10' },
      { day: 'Monday', time: '10:30-11:30', type: 'tutorial', group: '11' },
    ],
  }

  it('hides unselected options for a lesson type once one is selected', () => {
    const offering = {
      courseNumber: '02340114',
      academicYear: 2025,
      semesterCode: 201,
      scheduleGroups: [
        { day: 'Sunday', time: '08:30-10:30', type: 'lecture', group: '10' },
        { day: 'Sunday', time: '09:30-11:30', type: 'lecture', group: '11' },
        { day: 'Monday', time: '10:30-11:30', type: 'tutorial', group: '20' },
      ],
    }
    const options = extractLessonOptions(offering)
    const events = buildScheduleGridEvents({
      courses: [
        {
          courseNumber: offering.courseNumber,
          courseTitle: 'Intro',
          selectedLessonEvents: [{ eventId: options[0].eventId, type: 'lecture', group: '10' }],
        },
      ],
      offeringsByCourse: { [offering.courseNumber]: offering },
    })

    expect(events.filter((event) => event.kind === 'selected')).toHaveLength(1)
    expect(events.filter((event) => event.kind === 'available')).toHaveLength(1)
    expect(events.some((event) => event.group === '11')).toBe(false)
  })

  it('excludes inactive course options unless focused', () => {
    const events = buildScheduleGridEvents({
      courses: [
        {
          courseNumber: offering.courseNumber,
          courseTitle: 'Intro',
          isActive: false,
        },
      ],
      offeringsByCourse: { [offering.courseNumber]: offering },
    })
    expect(events).toHaveLength(0)
  })

  it('renders maybe courses with distinct kinds', () => {
    const options = extractLessonOptions(offering)
    const events = buildScheduleGridEvents({
      courses: [],
      maybeCourses: [
        {
          courseNumber: offering.courseNumber,
          courseTitle: 'Maybe Intro',
          selectedLessonEvents: [{ eventId: options[0].eventId, type: 'lecture', group: '10' }],
        },
      ],
      offeringsByCourse: { [offering.courseNumber]: offering },
    })

    expect(events.filter((event) => event.kind === 'maybe')).toHaveLength(1)
    expect(events.filter((event) => event.kind === 'maybe-available')).toHaveLength(1)
  })

  it('flags maybe-available slots that overlap selected courses', () => {
    const selectedOffering = {
      courseNumber: '02340114',
      academicYear: 2025,
      semesterCode: 201,
      scheduleGroups: [{ day: 'Sunday', time: '08:30-10:30', type: 'lecture', group: '10' }],
    }
    const maybeOffering = {
      courseNumber: '00999999',
      academicYear: 2025,
      semesterCode: 201,
      scheduleGroups: [{ day: 'Sunday', time: '09:00-11:00', type: 'lecture', group: '1' }],
    }
    const selectedOptions = extractLessonOptions(selectedOffering)
    const events = buildScheduleGridEvents({
      courses: [
        {
          courseNumber: '02340114',
          courseTitle: 'Selected',
          selectedLessonEvents: [{ eventId: selectedOptions[0].eventId, type: 'lecture' }],
        },
      ],
      maybeCourses: [{ courseNumber: '00999999', courseTitle: 'Maybe overlap' }],
      offeringsByCourse: {
        '02340114': selectedOffering,
        '00999999': maybeOffering,
      },
    })

    const maybeAvailable = events.find((event) => event.kind === 'maybe-available')
    expect(maybeAvailable?.previewConflict).toBe(true)
  })

  it('includes maybe selected slots in conflict baseline for other courses', () => {
    const offeringA = {
      courseNumber: '02340114',
      academicYear: 2025,
      semesterCode: 201,
      scheduleGroups: [{ day: 'Sunday', time: '08:30-10:30', type: 'lecture', group: '10' }],
    }
    const offeringB = {
      courseNumber: '00999999',
      academicYear: 2025,
      semesterCode: 201,
      scheduleGroups: [{ day: 'Sunday', time: '09:00-11:00', type: 'lecture', group: '1' }],
    }
    const optionsB = extractLessonOptions(offeringB)
    const events = buildScheduleGridEvents({
      courses: [
        {
          courseNumber: '02340114',
          courseTitle: 'Selected',
          selectedLessonEvents: [{ eventId: extractLessonOptions(offeringA)[0].eventId, type: 'lecture' }],
        },
      ],
      maybeCourses: [
        {
          courseNumber: '00999999',
          courseTitle: 'Maybe selected',
          selectedLessonEvents: [{ eventId: optionsB[0].eventId, type: 'lecture' }],
        },
      ],
      offeringsByCourse: {
        '02340114': offeringA,
        '00999999': offeringB,
      },
    })

    expect(events.some((event) => event.kind === 'maybe')).toBe(true)
    expect(events.some((event) => event.kind === 'selected')).toBe(true)
  })

  it('uses only selected events for conflict checks', () => {
    const options = extractLessonOptions(offering)
    const selected = selectedGridEventsFromCourses(
      [
        {
          courseNumber: '02340114',
          courseTitle: 'A',
          selectedLessonEvents: [{ eventId: options[0].eventId, type: 'lecture' }],
        },
      ],
      { '02340114': offering },
    )
    const candidate = buildScheduleGridEvents({
      courses: [{ courseNumber: '00999999', courseTitle: 'B' }],
      offeringsByCourse: {
        '00999999': {
          ...offering,
          courseNumber: '00999999',
          scheduleGroups: [{ day: 'Sunday', time: '09:00-11:00', type: 'lecture', group: '1' }],
        },
      },
    }).find((event) => event.kind === 'available')

    expect(candidate).toBeTruthy()
    expect(wouldLessonConflict(selected, candidate!)).toBe(true)
  })
})
