import { describe, expect, it } from 'vitest'
import {
  conflictsToGridBounds,
  collectGridEvents,
  gridColumnIndex,
  parseTimeRange,
  slotsOverlap,
  weekGridDays,
} from './planner'

describe('planner utilities', () => {
  it('parses hyphen time ranges', () => {
    expect(parseTimeRange('10:30 - 12:30')).toEqual({ start: 630, end: 750 })
  })

  it('detects overlap', () => {
    const left = { day: 'Sunday', start: 630, end: 750 }
    const right = { day: 'Sunday', start: 690, end: 810 }
    expect(slotsOverlap(left, right)).toBe(true)
  })

  it('treats adjacent slots as non-overlapping', () => {
    const left = { day: 'Sunday', start: 630, end: 750 }
    const right = { day: 'Sunday', start: 750, end: 870 }
    expect(slotsOverlap(left, right)).toBe(false)
  })

  it('ignores different days', () => {
    const left = { day: 'Sunday', start: 630, end: 750 }
    const right = { day: 'Monday', start: 630, end: 750 }
    expect(slotsOverlap(left, right)).toBe(false)
  })

  it('keeps Sunday through Thursday even when some weekdays have no events', () => {
    expect(weekGridDays('en', ['Sunday', 'Wednesday'])).toEqual([
      'Sunday',
      'Monday',
      'Tuesday',
      'Wednesday',
      'Thursday',
    ])
  })

  it('maps English event days onto Hebrew grid columns', () => {
    const columns = weekGridDays('he', ['Sunday'])
    expect(gridColumnIndex(columns, 'Sunday')).toBe(0)
    expect(columns[0]).toBe('ראשון')
  })

  it('adds Friday only when an event exists on Friday', () => {
    expect(weekGridDays('he', ['ראשון', 'שישי'])).toEqual([
      'ראשון',
      'שני',
      'שלישי',
      'רביעי',
      'חמישי',
      'שישי',
    ])
    expect(weekGridDays('he', ['ראשון', 'שלישי'])).toEqual([
      'ראשון',
      'שני',
      'שלישי',
      'רביעי',
      'חמישי',
    ])
  })

  it('does not duplicate custom blocks when schedule already includes CUSTOM slots', () => {
    const schedule = {
      weekView: [
        {
          day: 'Sunday',
          slots: [
            {
              day: 'Sunday',
              timeRange: '09:00-10:00',
              courseNumber: 'CUSTOM',
              courseTitle: 'Gym',
              slotType: 'custom',
            },
          ],
        },
      ],
    }
    const events = collectGridEvents(schedule, [{ id: '1', title: 'Gym', day: 'Sunday', startTime: '09:00', endTime: '10:00' }])
    expect(events.filter((event) => event.courseTitle === 'Gym')).toHaveLength(1)
  })

  it('uses pending custom blocks when customEventsDirty is true', () => {
    const schedule = {
      weekView: [
        {
          day: 'Sunday',
          slots: [
            {
              day: 'Sunday',
              timeRange: '09:00-10:00',
              courseNumber: 'CUSTOM',
              courseTitle: 'Old gym',
              slotType: 'custom',
            },
          ],
        },
      ],
    }
    const events = collectGridEvents(
      schedule,
      [{ id: '1', title: 'New gym', day: 'Sunday', startTime: '11:00', endTime: '12:00' }],
      [],
      true,
    )
    expect(events.map((event) => event.courseTitle)).toEqual(['New gym'])
  })

  it('maps schedule conflicts to grid bounds', () => {
    expect(
      conflictsToGridBounds([
        {
          day: 'Sunday',
          timeRange: '10:30 - 12:30',
          courseNumbers: ['01040001', '01040002'],
        },
      ]),
    ).toEqual([
      {
        day: 'Sunday',
        startMinutes: 630,
        endMinutes: 750,
        courseNumbers: ['01040001', '01040002'],
      },
    ])
  })
})
