import { describe, expect, it } from 'vitest'
import {
  displayTitleForParsedCourse,
  localizeParseWarning,
  previewCourseSearchHaystack,
} from './transcriptImportDisplay'
import type { ParsedTranscriptCourse } from '../types/api'

const parsedCourse = (overrides: Partial<ParsedTranscriptCourse> = {}): ParsedTranscriptCourse => ({
  courseNumber: '00940345',
  semesterCode: '2024-1',
  grade: 88,
  creditsEarned: 5,
  confidence: 0.95,
  warnings: [],
  title: 'Discrete Mathematics',
  ...overrides,
})

describe('transcriptImportDisplay', () => {
  const t = (key: string) =>
    ({
      'transcript.upload.warnings.noCourseRows': 'לא זוהו שורות קורס',
      'transcript.upload.warnings.titleNotDetected': 'שם קורס לא זוהה',
    })[key] ?? key

  it('localizes known parser warnings', () => {
    expect(localizeParseWarning('No course rows detected in transcript text.', t)).toBe(
      'לא זוהו שורות קורס',
    )
    expect(localizeParseWarning('Unknown parser message', t)).toBe('Unknown parser message')
  })

  it('prefers catalog title for the active locale', () => {
    const catalog = new Map([
      [
        '00940345',
        {
          courseNumber: '00940345',
          title: 'Discrete Mathematics',
          titleHebrew: 'מתמטיקה דיסקרטית',
        },
      ],
    ])

    expect(displayTitleForParsedCourse(parsedCourse(), catalog, 'he')).toBe('מתמטיקה דיסקרטית')
    expect(displayTitleForParsedCourse(parsedCourse(), catalog, 'en')).toBe('Discrete Mathematics')
  })

  it('falls back to PDF title when catalog lookup misses', () => {
    expect(displayTitleForParsedCourse(parsedCourse(), new Map(), 'he')).toBe('Discrete Mathematics')
  })

  it('builds search haystack from localized title', () => {
    const haystack = previewCourseSearchHaystack(
      parsedCourse({ title: 'Discrete Mathematics' }),
      'מתמטיקה דיסקרטית',
    )
    expect(haystack).toContain('מתמטיקה דיסקרטית')
    expect(haystack).toContain('00940345')
  })
})
