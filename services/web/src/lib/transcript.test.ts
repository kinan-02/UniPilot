import { describe, expect, it } from 'vitest'
import {
  compareSemesterCodesDesc,
  computeTranscriptStats,
  filterTranscriptRecords,
  gradeBadgeTone,
  groupTranscriptBySemester,
  isManualTranscriptRecord,
  sourceBadgeTone,
} from './transcript'
import type { CompletedCourse } from '../types/api'

const sampleRecord = (overrides: Partial<CompletedCourse> = {}): CompletedCourse => ({
  id: '1',
  courseId: 'c1',
  courseNumber: '00940345',
  courseTitle: 'Discrete Mathematics',
  semesterCode: '2024-1',
  grade: '85',
  creditsEarned: 5,
  attempt: 1,
  source: 'manual',
  ...overrides,
})

describe('transcript utilities', () => {
  it('computes transcript stats', () => {
    const stats = computeTranscriptStats([
      sampleRecord({ courseId: 'c1' }),
      sampleRecord({
        id: '2',
        courseId: 'c2',
        grade: '70',
        creditsEarned: 3,
        source: 'official',
        semesterCode: '2025-1',
      }),
    ])

    expect(stats.courseCount).toBe(2)
    expect(stats.totalCredits).toBe(8)
    expect(stats.averageGrade).toBeCloseTo(79.375)
    expect(stats.manualCount).toBe(1)
    expect(stats.readOnlyCount).toBe(1)
    expect(stats.semesterCount).toBe(2)
    expect(stats.earliestSemesterCode).toBe('2024-1')
    expect(stats.latestSemesterCode).toBe('2025-1')
  })

  it('excludes failed courses from accumulated credits and weighted average', () => {
    const stats = computeTranscriptStats([
      sampleRecord({ grade: '88', creditsEarned: 4 }),
      sampleRecord({
        id: '2',
        grade: '40',
        creditsEarned: 5,
        semesterCode: '2023-2',
      }),
      sampleRecord({
        id: '3',
        grade: '0',
        creditsEarned: 0,
        semesterCode: '2022-1',
      }),
    ])

    expect(stats.totalCredits).toBe(4)
    expect(stats.averageGrade).toBe(88)
  })

  it('uses gradePoints for exemptions and dedupes retakes by courseId', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'exempt-1',
        grade: '0',
        gradePoints: 82,
        creditsEarned: 3,
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '40',
        creditsEarned: 0,
        semesterCode: '2023-1',
      }),
      sampleRecord({
        id: '3',
        courseId: 'c1',
        grade: '88',
        creditsEarned: 3.5,
        semesterCode: '2024-1',
      }),
    ])

    expect(stats.totalCredits).toBe(6.5)
    expect(stats.courseCount).toBe(2)
    expect(stats.averageGrade).toBeCloseTo(85.231, 2)
  })

  it('groups records by semester newest first', () => {
    const groups = groupTranscriptBySemester([
      sampleRecord({ id: '1', courseId: 'c1', semesterCode: '2023-2' }),
      sampleRecord({ id: '2', courseId: 'c2', semesterCode: '2024-1', courseNumber: '00940411' }),
      sampleRecord({ id: '3', courseId: 'c3', semesterCode: '2024-1', courseNumber: '00940345' }),
    ])

    expect(groups.map((group) => group.semesterCode)).toEqual(['2024-1', '2023-2'])
    expect(groups[0].courses).toHaveLength(2)
    expect(groups[0].semesterCredits).toBe(10)
  })

  it('filters records by course number or title', () => {
    const records = [
      sampleRecord(),
      sampleRecord({ id: '2', courseNumber: '00940411', courseTitle: 'Algorithms' }),
    ]

    expect(filterTranscriptRecords(records, 'algorithms')).toHaveLength(1)
    expect(filterTranscriptRecords(records, '00940345')).toHaveLength(1)
  })

  it('orders semesters descending', () => {
    expect(compareSemesterCodesDesc('2024-2', '2024-1')).toBeLessThan(0)
    expect(compareSemesterCodesDesc('2025-1', '2024-2')).toBeLessThan(0)
  })

  it('maps grade tones and manual records', () => {
    expect(gradeBadgeTone('90')).toBe('success')
    expect(gradeBadgeTone('62')).toBe('neutral')
    expect(gradeBadgeTone('56')).toBe('warning')
    expect(gradeBadgeTone('40')).toBe('danger')
    expect(isManualTranscriptRecord(sampleRecord())).toBe(true)
    expect(isManualTranscriptRecord(sampleRecord({ source: 'official' }))).toBe(false)
    expect(isManualTranscriptRecord(sampleRecord({ source: 'imported' }))).toBe(false)
    expect(sourceBadgeTone('imported')).toBe('success')
    expect(sourceBadgeTone('official')).toBe('primary')
  })
})
