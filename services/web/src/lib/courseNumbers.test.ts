import { describe, expect, it } from 'vitest'
import { canonicalCourseNumber, courseNumberKeys } from './courseNumbers'

describe('courseNumbers', () => {
  it('normalizes Technion numbers to 8-digit 0-prefixed strings', () => {
    expect(canonicalCourseNumber('0940345')).toBe('00940345')
    expect(canonicalCourseNumber('00940345')).toBe('00940345')
  })

  it('returns both aliases for padded inputs', () => {
    expect(courseNumberKeys('0940345')).toEqual(['0940345', '00940345'])
    expect(courseNumberKeys('00940345')).toEqual(['00940345'])
  })
})
