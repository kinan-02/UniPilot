import type { CourseSummary } from '../types/api'
import type { Locale } from '../i18n/types'

export function courseTitle(course: CourseSummary, locale: Locale): string {
  if (locale === 'he') {
    return course.titleHebrew ?? course.title ?? course.courseNumber
  }
  return course.title ?? course.titleHebrew ?? course.courseNumber
}

export function normalizeScheduleGroup(group: Record<string, string>) {
  return {
    day: group.day ?? group.Day ?? group['יום'] ?? '',
    time: group.time ?? group.Time ?? group['שעה'] ?? '',
    type: group.type ?? group.Type ?? group['סוג'] ?? '',
  }
}

export class PlanningProfileError extends Error {
  readonly code: 'profile_required' | 'degree_required'

  constructor(code: 'profile_required' | 'degree_required') {
    super(code)
    this.name = 'PlanningProfileError'
    this.code = code
  }
}

export async function ensurePlanningProfile(
  getProfile: () => Promise<{ profile: { degreeId?: string | null } } | null>,
): Promise<void> {
  const existing = await getProfile()
  if (!existing?.profile) {
    throw new PlanningProfileError('profile_required')
  }
  if (!existing.profile.degreeId) {
    throw new PlanningProfileError('degree_required')
  }
}
