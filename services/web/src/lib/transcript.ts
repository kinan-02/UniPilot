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

/** Prefer the official numeric grade when present; exemptions may store points separately. */
export function resolveEffectiveTranscriptGrade(record: CompletedCourse): number | null {
  const grade = parseTranscriptGrade(record.grade)
  if (grade != null && grade > 0) return grade
  if (record.gradePoints != null) {
    const points = parseTranscriptGrade(record.gradePoints)
    if (points != null) return points
  }
  return grade
}

function parseRecordedAtTimestamp(value: string | undefined): number {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function semesterCodeRank(semesterCode: string): [number, number] {
  const parsed = parseSemesterCode(semesterCode)
  if (!parsed) return [0, 0]
  return [parsed.academicYear, parsed.termIndex]
}

function compareLatestAttemptPrecedence(
  left: CompletedCourse,
  right: CompletedCourse,
): number {
  const [leftYear, leftTerm] = semesterCodeRank(left.semesterCode)
  const [rightYear, rightTerm] = semesterCodeRank(right.semesterCode)
  if (leftYear !== rightYear) return leftYear - rightYear
  if (leftTerm !== rightTerm) return leftTerm - rightTerm
  const leftAttempt = left.attempt ?? 1
  const rightAttempt = right.attempt ?? 1
  if (leftAttempt !== rightAttempt) return leftAttempt - rightAttempt
  const leftRecorded = parseRecordedAtTimestamp(left.recordedAt)
  const rightRecorded = parseRecordedAtTimestamp(right.recordedAt)
  if (leftRecorded !== rightRecorded) return leftRecorded - rightRecorded
  return 0
}

/** Latest transcript row per courseId, regardless of pass/fail. */
export function pickLatestAttemptRecords(records: CompletedCourse[]): CompletedCourse[] {
  const latestByCourseId = new Map<string, CompletedCourse>()

  for (const record of records) {
    const existing = latestByCourseId.get(record.courseId)
    if (!existing || compareLatestAttemptPrecedence(record, existing) > 0) {
      latestByCourseId.set(record.courseId, record)
    }
  }

  return [...latestByCourseId.values()]
}

export function isPassingTranscriptRecord(record: CompletedCourse): boolean {
  const grade = resolveEffectiveTranscriptGrade(record)
  if (grade == null) return false
  return grade >= PASSING_GRADE_THRESHOLD
}

export function isExemptionTranscriptRecord(record: CompletedCourse): boolean {
  if (record.metadata?.exemption) return true
  const grade = parseTranscriptGrade(record.grade)
  return grade === 0 && (record.creditsEarned ?? 0) === 0
}

/** Pass rows are stored with a synthetic grade; they earn credits but not GPA points. */
export function isPassGradeTranscriptRecord(record: CompletedCourse): boolean {
  if (record.metadata?.passGrade === true) return true
  // Legacy PDF imports encoded Technion "Pass" as numeric 56 before metadata existed.
  if (
    (record.source === 'imported' || record.source === 'import') &&
    parseTranscriptGrade(record.grade) === 56
  ) {
    return true
  }
  return false
}

export function countsOnTranscriptSummary(record: CompletedCourse): boolean {
  if (isExemptionTranscriptRecord(record)) return true
  return isPassingTranscriptRecord(record)
}

/** Latest row per course that still appears on the official transcript summary. */
export function pickTranscriptSummaryRecords(records: CompletedCourse[]): CompletedCourse[] {
  return pickLatestAttemptRecords(records).filter(countsOnTranscriptSummary)
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
  if (isExemptionTranscriptRecord(record) || isPassGradeTranscriptRecord(record)) return false
  if ((record.creditsEarned ?? 0) <= 0) return false
  const grade = resolveEffectiveTranscriptGrade(record)
  if (grade == null) return false
  return !isFailedTranscriptGrade(grade)
}

/** One effective row per courseId — latest attempt only, and it must be passing. */
export function pickEffectiveTranscriptRecords(records: CompletedCourse[]): CompletedCourse[] {
  return pickLatestAttemptRecords(records).filter(isPassingTranscriptRecord)
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
  const summaryRecords = pickTranscriptSummaryRecords(records)
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

  for (const record of summaryRecords) {
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
    courseCount: summaryRecords.length,
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
  const latestByCourseId = new Map(
    pickLatestAttemptRecords(records).map((record) => [record.courseId, record]),
  )

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
      semesterCredits: courses.reduce((sum, course) => {
        const latest = latestByCourseId.get(course.courseId)
        if (!latest || latest.semesterCode !== semesterCode) return sum
        if (!countsTowardAccumulatedCredits(latest)) return sum
        return sum + (latest.creditsEarned ?? 0)
      }, 0),
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
