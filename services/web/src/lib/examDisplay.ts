import type { ExamSummaryItem } from '../types/api'

export type ExamMoedSection = 'A' | 'B' | 'other'

export type ExamListEntry =
  | { type: 'exam'; exam: ExamSummaryItem }
  | { type: 'gap'; days: number }

export function moedSection(moed?: string | null): ExamMoedSection {
  const normalized = String(moed ?? '').trim()
  const lower = normalized.toLowerCase()
  if (
    lower === 'a' ||
    lower.includes('exama') ||
    lower.includes('moeda') ||
    lower.includes('moed_a') ||
    normalized.includes('מועד א')
  ) {
    return 'A'
  }
  if (
    lower === 'b' ||
    lower.includes('examb') ||
    lower.includes('moedb') ||
    lower.includes('moed_b') ||
    normalized.includes('מועד ב')
  ) {
    return 'B'
  }
  return 'other'
}

function compareExams(left: ExamSummaryItem, right: ExamSummaryItem): number {
  const dateCompare = (left.date ?? '').localeCompare(right.date ?? '')
  if (dateCompare !== 0) return dateCompare
  const timeCompare = (left.startTime ?? '').localeCompare(right.startTime ?? '')
  if (timeCompare !== 0) return timeCompare
  return left.courseNumber.localeCompare(right.courseNumber)
}

export function daysBetweenDates(fromDate: string, toDate: string): number {
  const start = new Date(`${fromDate}T00:00:00`)
  const end = new Date(`${toDate}T00:00:00`)
  return Math.round((end.getTime() - start.getTime()) / 86_400_000)
}

export function examsWithGaps(exams: ExamSummaryItem[]): ExamListEntry[] {
  const sorted = [...exams].filter((exam) => exam.date).sort(compareExams)
  const entries: ExamListEntry[] = []

  sorted.forEach((exam, index) => {
    entries.push({ type: 'exam', exam })
    const next = sorted[index + 1]
    if (next?.date && exam.date) {
      const days = daysBetweenDates(exam.date, next.date)
      if (days > 0) entries.push({ type: 'gap', days })
    }
  })

  return entries
}

export function groupExamsByMoed(exams: ExamSummaryItem[]) {
  const scheduled = exams.filter((exam) => exam.date)
  return {
    moedA: scheduled.filter((exam) => moedSection(exam.moed) === 'A').sort(compareExams),
    moedB: scheduled.filter((exam) => moedSection(exam.moed) === 'B').sort(compareExams),
    other: scheduled.filter((exam) => moedSection(exam.moed) === 'other').sort(compareExams),
  }
}

export function formatExamDate(date: string, locale: 'he' | 'en'): string {
  const [year, month, day] = date.split('-').map(Number)
  if (!year || !month || !day) return date
  const value = new Date(year, month - 1, day)
  return value.toLocaleDateString(locale === 'he' ? 'he-IL' : 'en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}
