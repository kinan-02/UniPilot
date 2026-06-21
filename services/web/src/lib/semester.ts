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
