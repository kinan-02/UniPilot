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

const PASSING_GRADE_THRESHOLD = 55

export function parseTranscriptGrade(grade: string | number | undefined): number | null {
  if (grade == null || grade === '') return null
  const numeric = typeof grade === 'number' ? grade : Number(grade)
  return Number.isFinite(numeric) ? numeric : null
}

/** Mirrors backend resolve_record_numeric_grade — gradePoints override raw grade. */
export function resolveEffectiveTranscriptGrade(record: CompletedCourse): number | null {
  if (record.gradePoints != null) {
    const points = parseTranscriptGrade(record.gradePoints)
    if (points != null) return points
  }
  return parseTranscriptGrade(record.grade)
}

export function isPassingTranscriptRecord(record: CompletedCourse): boolean {
  const grade = resolveEffectiveTranscriptGrade(record)
  if (grade == null) return false
  return grade >= PASSING_GRADE_THRESHOLD
}

/** Technion transcript failures are strictly between 0 and the minimum pass grade. */
export function isFailedTranscriptGrade(grade: number | null): boolean {
  if (grade == null) return false
  return grade > 0 && grade < PASSING_GRADE_THRESHOLD
}

export function countsTowardAccumulatedCredits(record: CompletedCourse): boolean {
  if ((record.creditsEarned ?? 0) <= 0) return false
  return isPassingTranscriptRecord(record)
}

export function countsTowardWeightedAverage(record: CompletedCourse): boolean {
  if ((record.creditsEarned ?? 0) <= 0) return false
  const grade = resolveEffectiveTranscriptGrade(record)
  if (grade == null) return false
  return !isFailedTranscriptGrade(grade)
}

/** One effective row per courseId — mirrors backend build_effective_completions. */
export function pickEffectiveTranscriptRecords(records: CompletedCourse[]): CompletedCourse[] {
  const bestByCourseId = new Map<string, CompletedCourse>()

  for (const record of records) {
    if (!isPassingTranscriptRecord(record)) continue

    const existing = bestByCourseId.get(record.courseId)
    if (!existing) {
      bestByCourseId.set(record.courseId, record)
      continue
    }

    const candidateCredits = record.creditsEarned ?? 0
    const existingCredits = existing.creditsEarned ?? 0
    if (candidateCredits > existingCredits) {
      bestByCourseId.set(record.courseId, record)
    }
  }

  return [...bestByCourseId.values()]
}

export function gradeBadgeTone(grade: string | number | undefined): 'success' | 'warning' | 'danger' | 'neutral' {
  const numeric = parseTranscriptGrade(grade)
  if (numeric == null) return 'neutral'
  if (numeric >= 85) return 'success'
  if (numeric >= 60) return 'neutral'
  if (numeric >= PASSING_GRADE_THRESHOLD) return 'warning'
  return 'danger'
}

export { compareSemesterCodesDesc } from './semester'

export function computeTranscriptStats(records: CompletedCourse[]): TranscriptStats {
  const effectiveRecords = pickEffectiveTranscriptRecords(records)
  let totalCredits = 0
  let weightedGradeSum = 0
  let weightedCreditTotal = 0
  let manualCount = 0
  let readOnlyCount = 0
  const semesterCodes = new Set<string>()

  for (const record of records) {
    if (record.source === 'manual') {
      manualCount += 1
    } else {
      readOnlyCount += 1
    }
  }

  for (const record of effectiveRecords) {
    semesterCodes.add(record.semesterCode)
    if (countsTowardAccumulatedCredits(record)) {
      totalCredits += record.creditsEarned ?? 0
    }

    if (countsTowardWeightedAverage(record)) {
      const grade = resolveEffectiveTranscriptGrade(record)
      const credits = record.creditsEarned ?? 0
      if (grade != null) {
        weightedGradeSum += grade * credits
        weightedCreditTotal += credits
      }
    }
  }

  const orderedSemesters = [...semesterCodes].sort(compareSemesterCodesDesc)

  return {
    courseCount: effectiveRecords.length,
    totalCredits,
    averageGrade: weightedCreditTotal > 0 ? weightedGradeSum / weightedCreditTotal : null,
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
      semesterCredits: pickEffectiveTranscriptRecords(courses).reduce(
        (sum, course) =>
          countsTowardAccumulatedCredits(course) ? sum + (course.creditsEarned ?? 0) : sum,
        0,
      ),
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
  if (source === 'imported' || source === 'import') return 'success'
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
