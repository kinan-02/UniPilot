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

  it('uses latest retake grade even when it is lower than an earlier attempt', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'c1',
        grade: '90',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2023-1',
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '62',
        creditsEarned: 3.5,
        attempt: 2,
        semesterCode: '2024-1',
      }),
    ])

    expect(stats.totalCredits).toBe(3.5)
    expect(stats.courseCount).toBe(1)
    expect(stats.averageGrade).toBe(62)
  })

  it('excludes a course when the latest retake attempt failed', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'c1',
        grade: '88',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2023-1',
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '40',
        creditsEarned: 0,
        attempt: 2,
        semesterCode: '2024-1',
      }),
    ])

    expect(stats.totalCredits).toBe(0)
    expect(stats.courseCount).toBe(0)
    expect(stats.averageGrade).toBeNull()
  })

  it('prefers later retake attempt when deduping transcript rows', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'c1',
        grade: '70',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2023-1',
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '88',
        creditsEarned: 3.5,
        attempt: 2,
        semesterCode: '2024-1',
      }),
    ])

    expect(stats.totalCredits).toBe(3.5)
    expect(stats.courseCount).toBe(1)
    expect(stats.averageGrade).toBe(88)
  })

  it('prefers later semester over higher attempt number for the same course', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'c1',
        grade: '88',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2024-2',
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '40',
        creditsEarned: 0,
        attempt: 2,
        semesterCode: '2023-1',
      }),
    ])

    expect(stats.totalCredits).toBe(3.5)
    expect(stats.averageGrade).toBe(88)
  })

  it('prefers later recordedAt when attempt numbers tie in the same semester', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'c1',
        grade: '70',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2024-1',
        recordedAt: '2024-01-01T00:00:00.000Z',
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '88',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2024-1',
        recordedAt: '2024-06-01T00:00:00.000Z',
      }),
    ])

    expect(stats.totalCredits).toBe(3.5)
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

  it('treats legacy imported pass rows encoded as 56 as non-GPA without metadata', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'pass-legacy',
        grade: '56',
        creditsEarned: 3,
        source: 'imported',
      }),
      sampleRecord({
        id: '2',
        courseId: 'numeric-1',
        grade: '90',
        creditsEarned: 4,
        source: 'imported',
      }),
    ])

    expect(stats.totalCredits).toBe(7)
    expect(stats.averageGrade).toBe(90)
  })

  it('counts exemptions and excludes pass grades from GPA like the official transcript', () => {
    const stats = computeTranscriptStats([
      sampleRecord({
        id: '1',
        courseId: 'exempt-1',
        grade: '0',
        creditsEarned: 0,
        metadata: { exemption: true },
      }),
      sampleRecord({
        id: '2',
        courseId: 'pass-1',
        grade: '56',
        creditsEarned: 3,
        metadata: { passGrade: true },
      }),
      sampleRecord({
        id: '3',
        courseId: 'numeric-1',
        grade: '90',
        creditsEarned: 4,
      }),
    ])

    expect(stats.courseCount).toBe(3)
    expect(stats.totalCredits).toBe(7)
    expect(stats.averageGrade).toBe(90)
  })

  it('matches official gradesheet totals after import (22 catalog-resolved rows)', () => {
    const records: CompletedCourse[] = [
      { id: '1', courseId: 'c1', semesterCode: '2022-1', grade: '0', creditsEarned: 0, attempt: 1, source: 'imported', metadata: { exemption: true } },
      { id: '2', courseId: 'c2', semesterCode: '2022-1', grade: '91', creditsEarned: 4, attempt: 1, source: 'imported' },
      { id: '3', courseId: 'c3', semesterCode: '2022-1', grade: '84', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '4', courseId: 'c4', semesterCode: '2022-1', grade: '0', creditsEarned: 0, attempt: 1, source: 'imported', metadata: { exemption: true } },
      { id: '5', courseId: 'c5', semesterCode: '2022-2', grade: '94', creditsEarned: 5.5, attempt: 1, source: 'imported' },
      { id: '6', courseId: 'c6', semesterCode: '2022-2', grade: '83', creditsEarned: 2.5, attempt: 1, source: 'imported' },
      { id: '7', courseId: 'c7', semesterCode: '2022-2', grade: '56', creditsEarned: 5.5, attempt: 1, source: 'imported', metadata: { passGrade: true } },
      { id: '8', courseId: 'c8', semesterCode: '2022-2', grade: '80', creditsEarned: 4, attempt: 1, source: 'imported' },
      { id: '9', courseId: 'c9', semesterCode: '2022-2', grade: '56', creditsEarned: 3, attempt: 1, source: 'imported', metadata: { passGrade: true } },
      { id: '10', courseId: 'c10', semesterCode: '2022-2', grade: '93', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '11', courseId: 'c11', semesterCode: '2022-3', grade: '83', creditsEarned: 3.5, attempt: 1, source: 'imported' },
      { id: '12', courseId: 'c12', semesterCode: '2023-1', grade: '84', creditsEarned: 5, attempt: 1, source: 'imported' },
      { id: '13', courseId: 'c13', semesterCode: '2023-1', grade: '76', creditsEarned: 4, attempt: 1, source: 'imported' },
      { id: '14', courseId: 'c14', semesterCode: '2023-1', grade: '74', creditsEarned: 5, attempt: 1, source: 'imported' },
      { id: '15', courseId: 'c15', semesterCode: '2023-2', grade: '86', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '16', courseId: 'c16', semesterCode: '2023-2', grade: '85', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '17', courseId: 'c17', semesterCode: '2023-2', grade: '73', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '18', courseId: 'c18', semesterCode: '2023-2', grade: '56', creditsEarned: 3, attempt: 1, source: 'imported', metadata: { passGrade: true } },
      { id: '19', courseId: 'c19', semesterCode: '2024-1', grade: '80', creditsEarned: 3.5, attempt: 1, source: 'imported' },
      { id: '20', courseId: 'c20', semesterCode: '2024-1', grade: '88', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '21', courseId: 'c21', semesterCode: '2024-1', grade: '82', creditsEarned: 3, attempt: 1, source: 'imported' },
      { id: '22', courseId: 'c22', semesterCode: '2024-1', grade: '95', creditsEarned: 1, attempt: 1, source: 'imported' },
    ]

    const stats = computeTranscriptStats(records)

    expect(stats.courseCount).toBe(22)
    expect(stats.totalCredits).toBe(70.5)
    expect(stats.averageGrade).toBeCloseTo(83.7, 1)
    expect(stats.semesterCount).toBe(6)
    expect(stats.readOnlyCount).toBe(22)
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

  it('semester credit totals follow the global latest attempt, not per-semester pass history', () => {
    const groups = groupTranscriptBySemester([
      sampleRecord({
        id: '1',
        courseId: 'c1',
        grade: '88',
        creditsEarned: 3.5,
        attempt: 1,
        semesterCode: '2023-2',
      }),
      sampleRecord({
        id: '2',
        courseId: 'c1',
        grade: '40',
        creditsEarned: 0,
        attempt: 2,
        semesterCode: '2024-1',
      }),
    ])

    expect(groups.find((group) => group.semesterCode === '2023-2')?.semesterCredits).toBe(0)
    expect(groups.find((group) => group.semesterCode === '2024-1')?.semesterCredits).toBe(0)
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
