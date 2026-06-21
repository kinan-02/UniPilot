import { describe, expect, it } from 'vitest'
import {
  buildSelectedGroupsFromOptions,
  groupOptionsFromOffering,
  hasPartialGroupSelection,
} from './scheduleGroups'

describe('scheduleGroups', () => {
  it('groups offering slots by canonical type', () => {
    const options = groupOptionsFromOffering([
      { type: 'הרצאה', day: 'Monday', time: '09:00-11:00' },
      { type: 'תרגול', day: 'Tuesday', time: '10:00-12:00' },
      { type: 'תרגול', day: 'Wednesday', time: '14:00-16:00' },
    ])
    expect(options.filter((opt) => opt.slotKey === 'lecture')).toHaveLength(1)
    expect(options.filter((opt) => opt.slotKey === 'tutorial')).toHaveLength(2)
    expect(options.filter((opt) => opt.slotKey === 'tutorial').map((opt) => opt.index)).toEqual([0, 1])
  })

  it('detects partial group selection', () => {
    expect(hasPartialGroupSelection(undefined)).toBe(false)
    expect(hasPartialGroupSelection({ lecture: 0 })).toBe(true)
    expect(hasPartialGroupSelection({ lecture: null, tutorial: null })).toBe(false)
  })

  it('updates selected groups immutably', () => {
    const next = buildSelectedGroupsFromOptions({ lecture: 1 }, 'tutorial', 0)
    expect(next).toEqual({ lecture: 1, tutorial: 0, lab: null, project: null })
  })
})
