const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const SEMESTER_CODE_PATTERN = /^\d{4}-[123]$/
const COURSE_NUMBER_PATTERN = /^0\d{7}$/
const PASSWORD_PATTERN = /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/

export type ValidationResult = { ok: true } | { ok: false; message: string }

export function validateEmail(value: string): ValidationResult {
  const trimmed = value.trim()
  if (!trimmed) return { ok: false, message: 'validation.emailRequired' }
  if (!EMAIL_PATTERN.test(trimmed) || trimmed.length > 254) {
    return { ok: false, message: 'validation.emailInvalid' }
  }
  return { ok: true }
}

export function validatePassword(value: string): ValidationResult {
  if (!value) return { ok: false, message: 'validation.passwordRequired' }
  if (!PASSWORD_PATTERN.test(value)) {
    return { ok: false, message: 'validation.passwordWeak' }
  }
  return { ok: true }
}

export function validateSemesterCode(value: string): ValidationResult {
  const trimmed = value.trim()
  if (!SEMESTER_CODE_PATTERN.test(trimmed)) {
    return { ok: false, message: 'validation.semesterCode' }
  }
  return { ok: true }
}

export function validateCredits(value: number): ValidationResult {
  if (Number.isNaN(value) || value < 0 || value > 36) {
    return { ok: false, message: 'validation.creditsRange' }
  }
  if (Math.round(value * 2) !== value * 2) {
    return { ok: false, message: 'validation.creditsRange' }
  }
  return { ok: true }
}

export function validatePlanName(value: string): ValidationResult {
  const trimmed = value.trim()
  if (!trimmed || trimmed.length > 120) {
    return { ok: false, message: 'validation.planName' }
  }
  return { ok: true }
}

export function validateCourseNumber(value: string): ValidationResult {
  const trimmed = value.trim()
  if (!COURSE_NUMBER_PATTERN.test(trimmed)) {
    return { ok: false, message: 'validation.courseNumber' }
  }
  return { ok: true }
}

export function isCourseNumberQuery(value: string): boolean {
  const digits = value.replace(/\D/g, '')
  return digits.length >= 3 && digits.length <= 8
}
