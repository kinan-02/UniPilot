import { describe, expect, it } from 'vitest'
import {
  validateEmail,
  validatePassword,
  validateSemesterCode,
  validateCredits,
  validatePlanName,
  validateCourseNumber,
} from './validation'

describe('validation', () => {
  it('validates email', () => {
    expect(validateEmail('')).toEqual({ ok: false, message: 'validation.emailRequired' })
    expect(validateEmail('bad')).toEqual({ ok: false, message: 'validation.emailInvalid' })
    expect(validateEmail('user@example.com')).toEqual({ ok: true })
  })

  it('validates password strength', () => {
    expect(validatePassword('short')).toEqual({ ok: false, message: 'validation.passwordWeak' })
    expect(validatePassword('StrongPass123!')).toEqual({ ok: true })
  })

  it('validates semester code', () => {
    expect(validateSemesterCode('2025-2')).toEqual({ ok: true })
    expect(validateSemesterCode('2025-3')).toEqual({ ok: true })
    expect(validateSemesterCode('25-2')).toEqual({ ok: false, message: 'validation.semesterCode' })
  })

  it('validates credits in half increments', () => {
    expect(validateCredits(12)).toEqual({ ok: true })
    expect(validateCredits(12.5)).toEqual({ ok: true })
    expect(validateCredits(12.25)).toEqual({ ok: false, message: 'validation.creditsRange' })
  })

  it('validates plan name length', () => {
    expect(validatePlanName('Spring plan')).toEqual({ ok: true })
    expect(validatePlanName('')).toEqual({ ok: false, message: 'validation.planName' })
  })

  it('validates technion course numbers', () => {
    expect(validateCourseNumber('00940345')).toEqual({ ok: true })
    expect(validateCourseNumber('123')).toEqual({ ok: false, message: 'validation.courseNumber' })
  })
})
