/** Map API semester code YYYY-1/2/3 to catalog offering semesterCode 200/201/202 */
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

export function defaultSemesterCode(): string {
  const now = new Date()
  const year = now.getFullYear()
  const month = now.getMonth() + 1
  const term = month >= 3 && month <= 8 ? 2 : 1
  return `${year}-${term}`
}

/** Upcoming semester codes for quick-pick UI (e.g. 2025-2, 2025-3, 2026-1). */
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
  if (locale === 'he') {
    const terms = ['סמסטר א׳', 'סמסטר ב׳', 'סמסטר קיץ']
    return `${parsed.academicYear} · ${terms[parsed.termIndex - 1] ?? code}`
  }
  const terms = ['Semester A', 'Semester B', 'Summer semester']
  return `${parsed.academicYear} · ${terms[parsed.termIndex - 1] ?? code}`
}
