import type { CourseOffering, ExamSummary, ExamSummaryItem } from '../types/api'
import type { ClientScheduleCourse } from './clientSchedulePreview'

const MOED_A_KEYS = new Set([
  'moedA',
  'moed_a',
  'examA',
  'exam_a',
  'Moed A',
  'מועד א',
  "מועד א'",
  'מועד א׳',
])

const MOED_B_KEYS = new Set([
  'moedB',
  'moed_b',
  'examB',
  'exam_b',
  'Moed B',
  'מועד ב',
  "מועד ב'",
  'מועד ב׳',
])

const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?/
const DMY_DATE_PATTERN = /^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})(?:[ T](\d{1,2}):(\d{2}))?/

function moedFromKey(key: string): string | null {
  const normalized = key.trim()
  if (MOED_A_KEYS.has(normalized)) return 'A'
  if (MOED_B_KEYS.has(normalized)) return 'B'
  const lower = normalized.toLowerCase()
  if (lower.includes('exama') || lower.includes('moeda') || lower.includes('moed_a')) return 'A'
  if (lower.includes('examb') || lower.includes('moedb') || lower.includes('moed_b')) return 'B'
  if (normalized.includes('מועד א')) return 'A'
  if (normalized.includes('מועד ב')) return 'B'
  return null
}

function parseExamDatetime(raw: string | null | undefined): {
  date: string | null
  startTime: string | null
  raw: string | null
} {
  if (!raw?.trim()) {
    return { date: null, startTime: null, raw: null }
  }

  const text = raw.trim()
  for (const pattern of [ISO_DATE_PATTERN, DMY_DATE_PATTERN]) {
    const match = text.match(pattern)
    if (!match) continue

    let year: number
    let month: number
    let day: number
    if (match[1]?.length === 4) {
      year = Number(match[1])
      month = Number(match[2])
      day = Number(match[3])
    } else {
      day = Number(match[1])
      month = Number(match[2])
      year = Number(match[3])
    }

    const startTime =
      match[4] !== undefined && match[5] !== undefined
        ? `${String(Number(match[4])).padStart(2, '0')}:${match[5]}`
        : null

    const date = new Date(year, month - 1, day)
    if (Number.isNaN(date.getTime())) continue

    const isoDate = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
    return { date: isoDate, startTime, raw: text }
  }

  return { date: null, startTime: null, raw: text }
}

export function examsFromOffering(
  offering: CourseOffering | undefined,
  courseNumber: string,
  courseName: string,
): ExamSummaryItem[] {
  const examDates = offering?.examDates
  if (!examDates || !Object.keys(examDates).length) return []

  const items: ExamSummaryItem[] = []
  for (const [key, value] of Object.entries(examDates)) {
    const parsed = parseExamDatetime(value)
    if (!parsed.date) continue
    items.push({
      courseNumber,
      courseName,
      moed: moedFromKey(key) ?? key,
      date: parsed.date,
      startTime: parsed.startTime,
      endTime: null,
      raw: parsed.raw,
      isMissing: false,
    })
  }
  return items
}

export function buildClientExamSummary(
  courses: ClientScheduleCourse[],
  offeringsByCourse: Record<string, CourseOffering | undefined>,
): ExamSummary {
  const entries = courses
    .filter((course) => course.isActive !== false)
    .flatMap((course) =>
      examsFromOffering(
        offeringsByCourse[course.courseNumber],
        course.courseNumber,
        course.courseTitle,
      ),
    )
    .filter((exam) => exam.date)
    .sort((left, right) => {
      const dateCompare = String(left.date).localeCompare(String(right.date))
      if (dateCompare !== 0) return dateCompare
      const timeCompare = String(left.startTime ?? '').localeCompare(String(right.startTime ?? ''))
      if (timeCompare !== 0) return timeCompare
      return left.courseNumber.localeCompare(right.courseNumber)
    })

  const byDate = new Map<string, string[]>()
  for (const entry of entries) {
    const dateKey = String(entry.date)
    const bucket = byDate.get(dateKey) ?? []
    bucket.push(entry.courseNumber)
    byDate.set(dateKey, bucket)
  }

  const warnings = [...byDate.entries()]
    .filter(([, courseNumbers]) => new Set(courseNumbers).size > 1)
    .map(([dateKey, courseNumbers]) => {
      const unique = [...new Set(courseNumbers)].sort()
      return {
        type: 'same_day_exams',
        date: dateKey,
        courseNumbers: unique,
        message: `Multiple exams on ${dateKey}: ${unique.join(', ')}`,
      }
    })

  return {
    exams: entries,
    warnings,
    totalExams: entries.length,
    missingCount: 0,
  }
}
