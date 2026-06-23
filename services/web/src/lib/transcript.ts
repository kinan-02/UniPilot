import { compareSemesterCodesDesc, parseSemesterCode } from './semester'
import type { CompletedCourse } from '../types/api'

export type TranscriptStats = {
  courseCount: number
  totalCredits: number
  averageGrade: number | null
  manualCount: number
  readOnlyCount: number
  semesterCount: number
  earliestSemesterCode: string | null
  latestSemesterCode: string | null
}

export type TranscriptSemesterGroup = {
  semesterCode: string
  courses: CompletedCourse[]
  semesterCredits: number
}

export function parseTranscriptGrade(grade: string | number | undefined): number | null {
  if (grade == null || grade === '') return null
  const numeric = typeof grade === 'number' ? grade : Number(grade)
  return Number.isFinite(numeric) ? numeric : null
}

export function gradeBadgeTone(grade: string | number | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
  const numeric = parseTranscriptGrade(grade)
  if (numeric == null) return 'neutral'
  if (numeric >= 85) return 'success'
  if (numeric >= 60) return 'neutral'
  if (numeric >= 55) return 'warning'
  return 'danger'
}

export { compareSemesterCodesDesc } from './semester'

export function computeTranscriptStats(records: CompletedCourse[]): TranscriptStats {
  let totalCredits = 0
  let gradeSum = 0
  let gradeCount = 0
  let manualCount = 0
  let readOnlyCount = 0
  const semesterCodes = new Set<string>()

  for (const record of records) {
    totalCredits += record.creditsEarned ?? 0
    semesterCodes.add(record.semesterCode)
    const grade = parseTranscriptGrade(record.grade)
    if (grade != null) {
      gradeSum += grade
      gradeCount += 1
    }
    if (record.source === 'manual') {
      manualCount += 1
    } else {
      readOnlyCount += 1
    }
  }

  const orderedSemesters = [...semesterCodes].sort(compareSemesterCodesDesc)

  return {
    courseCount: records.length,
    totalCredits,
    averageGrade: gradeCount > 0 ? gradeSum / gradeCount : null,
    manualCount,
    readOnlyCount,
    semesterCount: semesterCodes.size,
    earliestSemesterCode: orderedSemesters.at(-1) ?? null,
    latestSemesterCode: orderedSemesters[0] ?? null,
  }
}

export function groupTranscriptBySemester(records: CompletedCourse[]): TranscriptSemesterGroup[] {
  const groups = new Map<string, CompletedCourse[]>()

  for (const record of records) {
    const existing = groups.get(record.semesterCode) ?? []
    existing.push(record)
    groups.set(record.semesterCode, existing)
  }

  return [...groups.entries()]
    .map(([semesterCode, courses]) => ({
      semesterCode,
      courses: [...courses].sort((left, right) =>
        (left.courseNumber ?? left.courseId).localeCompare(right.courseNumber ?? right.courseId),
      ),
      semesterCredits: courses.reduce((sum, course) => sum + (course.creditsEarned ?? 0), 0),
    }))
    .sort((left, right) => compareSemesterCodesDesc(left.semesterCode, right.semesterCode))
}

export function filterTranscriptRecords(
  records: CompletedCourse[],
  query: string,
): CompletedCourse[] {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return records

  return records.filter((record) => {
    const haystack = [
      record.courseNumber,
      record.courseId,
      record.courseTitle,
      record.semesterCode,
      record.grade,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(normalized)
  })
}

export function isManualTranscriptRecord(record: CompletedCourse): boolean {
  return record.source === 'manual'
}

export function sourceBadgeTone(source: string): 'neutral' | 'primary' | 'success' {
  if (source === 'official') return 'primary'
  if (source === 'import') return 'success'
  return 'neutral'
}

export function formatTranscriptAcademicSpan(
  earliestSemesterCode: string | null,
  latestSemesterCode: string | null,
  locale: 'he' | 'en',
): string | null {
  if (!earliestSemesterCode || !latestSemesterCode) return null
  const earliest = parseSemesterCode(earliestSemesterCode)
  const latest = parseSemesterCode(latestSemesterCode)
  if (!earliest || !latest) return null

  const start = earliest.academicYear
  const end = latest.academicYear + 1
  if (start === latest.academicYear && earliestSemesterCode === latestSemesterCode) {
    return locale === 'he' ? `שנה אקדמית ${start}–${end}` : `Academic year ${start}–${end}`
  }
  return locale === 'he'
    ? `שנים אקדמיות ${start}–${end}`
    : `Academic years ${start}–${end}`
}
