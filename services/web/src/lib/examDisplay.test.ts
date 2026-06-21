import { describe, expect, it } from 'vitest'
import { daysBetweenDates, examsWithGaps, groupExamsByMoed } from './examDisplay'
import type { ExamSummaryItem } from '../types/api'

describe('examDisplay', () => {
  const sampleExams: ExamSummaryItem[] = [
    {
      courseNumber: '02340114',
      courseName: 'Intro',
      moed: 'A',
      date: '2025-06-01',
      startTime: '09:00',
    },
    {
      courseNumber: '00960556',
      courseName: 'Options',
      moed: 'A',
      date: '2025-06-15',
      startTime: '10:00',
    },
    {
      courseNumber: '00960267',
      courseName: 'Security',
      moed: 'B',
      date: '2025-08-01',
      startTime: '09:00',
    },
  ]

  it('groups catalog examA and examB moeds into separate sections', () => {
    const grouped = groupExamsByMoed([
      {
        courseNumber: '02340114',
        courseName: 'Intro',
        moed: 'examA',
        date: '2025-06-01',
      },
      {
        courseNumber: '00960556',
        courseName: 'Options',
        moed: 'A',
        date: '2025-06-15',
      },
      {
        courseNumber: '00960267',
        courseName: 'Security',
        moed: 'examB',
        date: '2025-08-01',
      },
    ])
    expect(grouped.moedA).toHaveLength(2)
    expect(grouped.moedB).toHaveLength(1)
    expect(grouped.other).toHaveLength(0)
  })

  it('groups exams by moed and sorts by date', () => {
    const grouped = groupExamsByMoed(sampleExams)
    expect(grouped.moedA.map((exam) => exam.courseNumber)).toEqual(['02340114', '00960556'])
    expect(grouped.moedB.map((exam) => exam.courseNumber)).toEqual(['00960267'])
  })

  it('inserts day gaps between consecutive exams in a moed section', () => {
    const entries = examsWithGaps(groupExamsByMoed(sampleExams).moedA)
    expect(entries.filter((entry) => entry.type === 'exam')).toHaveLength(2)
    expect(entries.find((entry) => entry.type === 'gap')).toEqual({ type: 'gap', days: 14 })
  })

  it('calculates whole-day differences between exam dates', () => {
    expect(daysBetweenDates('2025-06-01', '2025-06-15')).toBe(14)
  })
})
