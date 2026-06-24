import { describe, expect, it } from 'vitest'
import {
  academicYearStartFromDate,
  buildTranscriptSemesterOptions,
  currentTermIndex,
  defaultSemesterCode,
  parseSemesterCode,
  pickDefaultPlannerSemester,
  semesterCodesInRange,
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

  it('labels semesters with academic year range', () => {
    expect(semesterLabel('2025-2', 'en')).toContain('2025-2026')
    expect(semesterLabel('2025-2', 'he')).toContain('2025-2026')
  })

  it('uses academic year start for spring calendar dates', () => {
    expect(academicYearStartFromDate(new Date('2026-06-15'))).toBe(2025)
    expect(currentTermIndex(new Date('2026-06-15'))).toBe(2)
    expect(defaultSemesterCode()).toMatch(/^\d{4}-[123]$/)
  })

  it('returns consecutive semester quick-pick options', () => {
    const options = upcomingSemesterCodes(3)
    expect(options).toHaveLength(3)
    options.forEach((code) => expect(parseSemesterCode(code)).not.toBeNull())
  })

  it('picks a catalog-backed default semester', () => {
    expect(pickDefaultPlannerSemester(['2025-1', '2025-2', '2025-3'])).toMatch(/^2025-[123]$/)
    expect(pickDefaultPlannerSemester(['2025-2'])).toBe('2025-2')
    expect(pickDefaultPlannerSemester([])).toBe(defaultSemesterCode())
  })

  it('suggests a localized plan name from semester code', () => {
    expect(suggestedPlanName('2025-2', 'en')).toContain('2025')
    expect(suggestedPlanName('2025-2', 'he')).toContain('תוכנית')
  })

  it('builds transcript semester options across many academic years', () => {
    const options = buildTranscriptSemesterOptions({
      catalogYear: 2021,
      currentSemesterCode: '2025-1',
      existingSemesterCodes: ['2019-2'],
    })

    expect(options).toContain('2019-2')
    expect(options).toContain('2021-1')
    expect(options).toContain('2025-1')
    expect(options.indexOf('2025-1')).toBeLessThan(options.indexOf('2019-2'))
    expect(semesterCodesInRange(2024, 2025)).toHaveLength(6)
  })
})
