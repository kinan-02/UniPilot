import { describe, expect, it } from 'vitest'
import { parseTimeRange } from './planner'

const GRID_STEP = 30

function eventGridSpan(startMinutes: number, endMinutes: number, min: number) {
  const startRow = Math.floor((startMinutes - min) / GRID_STEP) + 2
  const span = Math.max(1, Math.ceil((endMinutes - startMinutes) / GRID_STEP))
  return { startRow, span }
}

describe('weekly grid event sizing', () => {
  it('spans four 30-minute rows for an 08:30-10:30 lecture', () => {
    const parsed = parseTimeRange('08:30-10:30')
    expect(parsed).toEqual({ start: 510, end: 630 })

    const min = 8 * 60
    const { startRow, span } = eventGridSpan(parsed!.start, parsed!.end, min)

    expect(startRow).toBe(3)
    expect(span).toBe(4)
  })
})
