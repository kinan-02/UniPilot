/** Normalize Technion course numbers to 8-digit 0-prefixed strings (matches API catalog). */
export function canonicalCourseNumber(value: string): string {
  const digits = value.replace(/\D/g, '')
  if (digits.length < 7 || digits.length > 9) {
    return value.trim()
  }
  return digits.padStart(8, '0').slice(-8)
}

export function courseNumberKeys(value: string): string[] {
  const trimmed = value.trim()
  if (!trimmed) return []
  const canonical = canonicalCourseNumber(trimmed)
  return canonical !== trimmed ? [trimmed, canonical] : [trimmed]
}

export function lookupByCourseNumberKeys<T>(
  map: Record<string, T>,
  courseNumber: string,
): T | undefined {
  for (const key of courseNumberKeys(courseNumber)) {
    const value = map[key]
    if (value != null) return value
  }
  return undefined
}
