import { catalogApi } from '../api/endpoints'
import { courseTitle } from './planning'
import type { Locale } from '../i18n/types'
import type { CourseSummary, ParsedTranscriptCourse } from '../types/api'

const PARSE_WARNING_KEYS: Record<string, string> = {
  'No course rows detected in transcript text.': 'transcript.upload.warnings.noCourseRows',
  'No extractable text found in PDF; OCR fallback may be required.':
    'transcript.upload.warnings.noExtractableText',
  'Course title not detected on row': 'transcript.upload.warnings.titleNotDetected',
  'Recorded as exemption without points': 'transcript.upload.warnings.exemptionWithoutPoints',
  'Recorded as exemption with points; verify credits':
    'transcript.upload.warnings.exemptionWithPoints',
  'Recorded as pass grade': 'transcript.upload.warnings.passGrade',
}

export function localizeParseWarning(
  message: string,
  t: (key: string, params?: Record<string, string | number>) => string,
): string {
  const key = PARSE_WARNING_KEYS[message]
  return key ? t(key) : message
}

export function displayTitleForParsedCourse(
  course: ParsedTranscriptCourse,
  catalogByNumber: Map<string, CourseSummary>,
  locale: Locale,
): string | null {
  const catalogCourse = catalogByNumber.get(course.courseNumber)
  if (catalogCourse) {
    return courseTitle(catalogCourse, locale)
  }
  if (!course.title) return null
  return course.title
}

export function previewCourseSearchHaystack(
  course: ParsedTranscriptCourse,
  displayTitle: string | null,
): string {
  return [course.courseNumber, displayTitle, course.title, course.semesterCode, String(course.grade)]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
}

export async function fetchCatalogSummariesByNumbers(
  courseNumbers: string[],
): Promise<Map<string, CourseSummary>> {
  const unique = [...new Set(courseNumbers.filter(Boolean))]
  if (!unique.length) return new Map()

  const entries = await Promise.all(
    unique.map(async (courseNumber) => {
      try {
        const { course } = await catalogApi.course(courseNumber)
        return [courseNumber, course] as const
      } catch {
        return [courseNumber, null] as const
      }
    }),
  )

  const map = new Map<string, CourseSummary>()
  for (const [courseNumber, course] of entries) {
    if (course) map.set(courseNumber, course)
  }
  return map
}
