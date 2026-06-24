import { describe, expect, it } from 'vitest'
import { buildClientExamSummary, examsFromOffering } from './clientExamSummary'
import type { CourseOffering } from '../types/api'

describe('clientExamSummary', () => {
  it('parses moed exam dates from offering catalog data', () => {
    const offering: CourseOffering = {
      courseNumber: '00940345',
      academicYear: 2025,
      semesterCode: 202,
      examDates: {
        moedA: '2026-02-15 09:30',
        moedB: '22.03.2026 14:00',
      },
    }

    const exams = examsFromOffering(offering, '00940345', 'Discrete Math')
    expect(exams).toHaveLength(2)
    expect(exams[0]?.moed).toBe('A')
    expect(exams[0]?.date).toBe('2026-02-15')
    expect(exams[0]?.startTime).toBe('09:30')
    expect(exams[1]?.moed).toBe('B')
    expect(exams[1]?.date).toBe('2026-03-22')
  })

  it('builds summary with same-day warnings', () => {
    const offerings = {
      '10001': {
        courseNumber: '10001',
        academicYear: 2025,
        semesterCode: 202,
        examDates: { moedA: '2026-02-15 09:00' },
      } satisfies CourseOffering,
      '10002': {
        courseNumber: '10002',
        academicYear: 2025,
        semesterCode: 202,
        examDates: { moedA: '2026-02-15 14:00' },
      } satisfies CourseOffering,
    }

    const summary = buildClientExamSummary(
      [
        { courseNumber: '10001', courseTitle: 'Course A', isActive: true },
        { courseNumber: '10002', courseTitle: 'Course B', isActive: true },
      ],
      offerings,
    )

    expect(summary.totalExams).toBe(2)
    expect(summary.warnings).toHaveLength(1)
    expect(summary.warnings?.[0]?.type).toBe('same_day_exams')
  })
})
