/** Map API semester code YYYY-1/2/3 to catalog offering semesterCode 200/201/202.
 *  YYYY is the Technion academic-year start (e.g. 2025-2 = spring of 2025-2026). */

export function parseSemesterCode(code: string): {
  academicYear: number
  semesterCode: number
  termIndex: number
} | null {
  const match = code.trim().match(/^(\d{4})-([123])$/)
  if (!match) return null
  const academicYear = Number(match[1])
  const termIndex = Number(match[2])
  return {
    academicYear,
    termIndex,
    semesterCode: 200 + termIndex - 1,
  }
}

/** Academic year start year for a calendar date (Technion: year begins ~October). */
export function academicYearStartFromDate(date: Date): number {
  const year = date.getFullYear()
  const month = date.getMonth() + 1
  return month >= 9 ? year : year - 1
}

/** Current term index: 1=fall/winter, 2=spring, 3=summer. */
export function currentTermIndex(date: Date): 1 | 2 | 3 {
  const month = date.getMonth() + 1
  if (month >= 9 || month <= 2) return 1
  if (month >= 3 && month <= 6) return 2
  return 3
}

export function defaultSemesterCode(): string {
  const now = new Date()
  const academicYear = academicYearStartFromDate(now)
  const term = currentTermIndex(now)
  return `${academicYear}-${term}`
}

/** Upcoming semester quick-pick options from the current academic term. */
export function upcomingSemesterCodes(count = 4): string[] {
  const parsed = parseSemesterCode(defaultSemesterCode())
  if (!parsed) return [defaultSemesterCode()]

  const options: string[] = []
  let year = parsed.academicYear
  let term = parsed.termIndex

  for (let i = 0; i < count; i += 1) {
    options.push(`${year}-${term}`)
    term += 1
    if (term > 3) {
      term = 1
      year += 1
    }
  }

  return options
}

export function compareSemesterCodesDesc(a: string, b: string): number {
  const parsedA = parseSemesterCode(a)
  const parsedB = parseSemesterCode(b)
  if (!parsedA && !parsedB) return b.localeCompare(a)
  if (!parsedA) return 1
  if (!parsedB) return -1
  if (parsedA.academicYear !== parsedB.academicYear) {
    return parsedB.academicYear - parsedA.academicYear
  }
  return parsedB.termIndex - parsedA.termIndex
}

export function compareSemesterCodesAsc(a: string, b: string): number {
  return -compareSemesterCodesDesc(a, b)
}

/** Default planner semester when the calendar term is not in the catalog-backed list. */
export function pickDefaultPlannerSemester(available: string[]): string {
  if (!available.length) return defaultSemesterCode()
  const preferred = defaultSemesterCode()
  if (available.includes(preferred)) return preferred
  const sorted = [...available].sort(compareSemesterCodesAsc)
  return sorted[sorted.length - 1] ?? preferred
}

/** All YYYY-1/2/3 codes from the start academic year through the end year (inclusive). */
export function semesterCodesInRange(fromAcademicYear: number, toAcademicYear: number): string[] {
  const start = Math.min(fromAcademicYear, toAcademicYear)
  const end = Math.max(fromAcademicYear, toAcademicYear)
  const codes: string[] = []

  for (let year = start; year <= end; year += 1) {
    for (let term = 1; term <= 3; term += 1) {
      codes.push(`${year}-${term}`)
    }
  }

  return codes
}

const DEFAULT_TRANSCRIPT_HISTORY_YEARS = 12

export type TranscriptSemesterOptionsInput = {
  catalogYear?: number | null
  currentSemesterCode?: string | null
  existingSemesterCodes?: string[]
  /** How many academic years before the anchor year to include (default 12 ≈ full degree + margin). */
  historyYears?: number
}

/**
 * Semester choices for transcript entry: supports first-years through graduating students
 * and anyone backfilling courses from prior years.
 */
export function buildTranscriptSemesterOptions({
  catalogYear,
  currentSemesterCode,
  existingSemesterCodes = [],
  historyYears = DEFAULT_TRANSCRIPT_HISTORY_YEARS,
}: TranscriptSemesterOptionsInput): string[] {
  const anchor =
    parseSemesterCode(currentSemesterCode ?? defaultSemesterCode()) ??
    parseSemesterCode(defaultSemesterCode())
  if (!anchor) return [defaultSemesterCode()]

  const earliestOnTranscript = existingSemesterCodes
    .map((code) => parseSemesterCode(code)?.academicYear)
    .filter((year): year is number => year != null)
  const earliestYear = earliestOnTranscript.length ? Math.min(...earliestOnTranscript) : anchor.academicYear

  const catalogAnchor = catalogYear ?? anchor.academicYear
  const fromYear = Math.min(
    catalogAnchor - 2,
    earliestYear,
    anchor.academicYear - historyYears,
  )
  const toYear = anchor.academicYear + 1

  const merged = new Set<string>([
    ...semesterCodesInRange(fromYear, toYear),
    ...existingSemesterCodes,
    currentSemesterCode ?? defaultSemesterCode(),
  ])

  return [...merged].sort(compareSemesterCodesDesc)
}

export function groupSemesterCodesByAcademicYear(codes: string[]): Array<{
  academicYear: number
  semesters: string[]
}> {
  const byYear = new Map<number, string[]>()

  for (const code of codes) {
    const parsed = parseSemesterCode(code)
    if (!parsed) continue
    const existing = byYear.get(parsed.academicYear) ?? []
    existing.push(code)
    byYear.set(parsed.academicYear, existing)
  }

  return [...byYear.entries()]
    .map(([academicYear, semesters]) => ({
      academicYear,
      semesters: [...semesters].sort(compareSemesterCodesDesc),
    }))
    .sort((left, right) => right.academicYear - left.academicYear)
}

export function suggestedPlanName(code: string, locale: 'he' | 'en'): string {
  const label = semesterLabel(code, locale)
  return locale === 'he' ? `תוכנית ${label}` : `Plan — ${label}`
}

export function semesterLabel(code: string, locale: 'he' | 'en'): string {
  const parsed = parseSemesterCode(code)
  if (!parsed) return code
  const yearRange = `${parsed.academicYear}-${parsed.academicYear + 1}`
  if (locale === 'he') {
    const terms = ['חורף (200)', 'אביב (201)', 'קיץ (202)']
    return `${yearRange} · ${terms[parsed.termIndex - 1] ?? code}`
  }
  const terms = ['Winter (200)', 'Spring (201)', 'Summer (202)']
  return `${yearRange} · ${terms[parsed.termIndex - 1] ?? code}`
}

/** Technion offering semester code shown in catalog APIs (200/201/202). */
export function offeringSemesterCode(planSemesterCode: string): string | null {
  return parseSemesterCode(planSemesterCode)?.semesterCode.toString() ?? null
}
