import { describe, expect, it } from 'vitest'
import { parseTimeRange, slotsOverlap } from './planner'

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
})
