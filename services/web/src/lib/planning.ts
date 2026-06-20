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

export async function ensurePlanningProfile(
  semesterCode: string,
  getProfile: () => Promise<{ profile: { id: string } } | null>,
  createProfile: (body: Record<string, unknown>) => Promise<unknown>,
): Promise<void> {
  const existing = await getProfile()
  if (existing?.profile) return

  const year = Number(semesterCode.split('-')[0]) || new Date().getFullYear()
  await createProfile({
    institutionId: 'technion',
    programType: 'BSc',
    catalogYear: year,
    currentSemesterCode: semesterCode,
  })
}
