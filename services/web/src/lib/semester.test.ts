import { describe, expect, it } from 'vitest'
import {
  parseSemesterCode,
  semesterLabel,
  suggestedPlanName,
  upcomingSemesterCodes,
} from './semester'

describe('semester helpers', () => {
  it('parses YYYY-term into offering codes', () => {
    expect(parseSemesterCode('2025-1')).toEqual({
      academicYear: 2025,
      termIndex: 1,
      semesterCode: 200,
    })
    expect(parseSemesterCode('2025-2')).toEqual({
      academicYear: 2025,
      termIndex: 2,
      semesterCode: 201,
    })
  })

  it('labels semesters per locale', () => {
    expect(semesterLabel('2025-2', 'en')).toContain('2025')
    expect(semesterLabel('2025-2', 'he')).toContain('2025')
  })

  it('returns consecutive semester quick-pick options', () => {
    const options = upcomingSemesterCodes(3)
    expect(options).toHaveLength(3)
    options.forEach((code) => expect(parseSemesterCode(code)).not.toBeNull())
  })

  it('suggests a localized plan name from semester code', () => {
    expect(suggestedPlanName('2025-2', 'en')).toContain('2025')
    expect(suggestedPlanName('2025-2', 'he')).toContain('תוכנית')
  })
})
