/** Client-side lesson event utilities (mirrors backend lesson_events). */

import type { CourseOffering, SelectedGroups, SelectedLessonEvent } from '../types/api'

const SLOT_ALIASES: Record<string, string[]> = {
  lecture: ['lecture', 'הרצאה', 'lec'],
  tutorial: ['tutorial', 'תרגול', 'recitation', 'lesson', 'תר'],
  lab: ['lab', 'מעבדה', 'laboratory'],
  project: ['project', 'פרויקט'],
  workshop: ['workshop', 'סדנה'],
}

export const LESSON_TYPE_ORDER = [
  'lecture',
  'tutorial',
  'lab',
  'project',
  'workshop',
  'other',
] as const

export type LessonOption = {
  eventId: string
  type: string
  group?: string | null
  index: number
  day: string
  startTime: string
  endTime: string
  timeRange: string
  slotTypeLabel: string
  instructor?: string | null
  location?: string | null
  notes?: string | null
  incomplete?: boolean
}

function slug(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '') || 'na'
}

export function normalizeLessonType(raw: string): string {
  const normalized = raw.trim().toLowerCase()
  if (!normalized) return 'other'
  for (const [canonical, aliases] of Object.entries(SLOT_ALIASES)) {
    if (aliases.some((alias) => normalized.includes(alias.toLowerCase()))) return canonical
  }
  return normalized
}

function normalizeGroup(group: Record<string, string | number>) {
  return {
    day: String(group.day || group.יום || ''),
    timeRange: String(group.time || group.שעה || ''),
    slotType: String(group.type || group.סוג || ''),
  }
}

function splitTimeRange(timeRange: string): { startTime: string; endTime: string } {
  const match = timeRange
    .replace(/[–—]/g, '-')
    .match(/^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$/)
  if (!match) return { startTime: '', endTime: '' }
  const [, sh, sm, eh, em] = match
  return { startTime: `${sh.padStart(2, '0')}:${sm}`, endTime: `${eh.padStart(2, '0')}:${em}` }
}

function extractGroupLabel(group: Record<string, string | number>): string | null {
  for (const key of ['group', 'groupNumber', 'קבוצה', 'מס.', 'number']) {
    const value = group[key]
    if (value != null && String(value).trim()) return String(value).trim()
  }
  return null
}

function extractInstructor(group: Record<string, string | number>): string | null {
  for (const key of ['instructor', 'מרצה/מתרגל', 'lecturer', 'ta']) {
    const value = group[key]
    if (value != null && String(value).trim()) return String(value).trim()
  }
  return null
}

function extractLocation(group: Record<string, string | number>): string | null {
  const building = group.building || group.בניין
  const room = group.room || group.חדר
  const parts = [building, room].filter((part) => part != null && String(part).trim())
  return parts.length ? parts.map(String).join(' ') : null
}

export function buildLessonEventId(args: {
  courseNumber: string
  academicYear: number
  semesterCode: number
  lessonType: string
  groupLabel?: string | null
  day: string
  startTime: string
  endTime: string
  location?: string | null
}): string {
  const parts = [
    args.courseNumber,
    String(args.academicYear),
    String(args.semesterCode),
    normalizeLessonType(args.lessonType),
    slug(args.groupLabel || '0'),
    slug(args.day),
    args.startTime.replace(':', ''),
    args.endTime.replace(':', ''),
  ]
  if (args.location) parts.push(slug(args.location))
  return parts.join('-')
}

export function lessonOptionFromGroup(
  group: Record<string, string | number>,
  args: {
    courseNumber: string
    academicYear: number
    semesterCode: number
    index: number
  },
): LessonOption {
  const normalized = normalizeGroup(group)
  const lessonType = normalizeLessonType(normalized.slotType)
  const groupLabel = extractGroupLabel(group)
  const { startTime, endTime } = splitTimeRange(normalized.timeRange)
  const location = extractLocation(group)
  const instructor = extractInstructor(group)
  const incomplete = !normalized.day || !startTime || !endTime

  const eventId = buildLessonEventId({
    courseNumber: args.courseNumber,
    academicYear: args.academicYear,
    semesterCode: args.semesterCode,
    lessonType,
    groupLabel,
    day: normalized.day,
    startTime: startTime || '0000',
    endTime: endTime || '0000',
    location,
  })

  return {
    eventId,
    type: lessonType,
    group: groupLabel,
    index: args.index,
    day: normalized.day,
    startTime,
    endTime,
    timeRange: normalized.timeRange,
    slotTypeLabel: normalized.slotType || lessonType,
    instructor,
    location,
    incomplete,
  }
}

export function extractLessonOptions(
  offering?: CourseOffering,
  courseNumber?: string,
): LessonOption[] {
  if (!offering?.scheduleGroups?.length) return []
  const number = courseNumber || offering.courseNumber || ''
  const academicYear = offering.academicYear ?? 0
  const semesterCode = offering.semesterCode ?? 0
  return offering.scheduleGroups.map((group, index) =>
    lessonOptionFromGroup(group as Record<string, string | number>, {
      courseNumber: number,
      academicYear,
      semesterCode,
      index,
    }),
  )
}

export function groupLessonOptionsByType(
  options: LessonOption[],
): Record<string, LessonOption[]> {
  return options.reduce<Record<string, LessonOption[]>>((acc, option) => {
    const key = option.type || 'other'
    acc[key] = acc[key] ?? []
    acc[key].push(option)
    return acc
  }, {})
}

function groupScheduleByType(scheduleGroups: Array<Record<string, string | number>>) {
  const grouped: Record<string, Array<{ index: number; group: Record<string, string | number> }>> = {}
  scheduleGroups.forEach((group, index) => {
    const key = normalizeLessonType(normalizeGroup(group).slotType)
    grouped[key] = grouped[key] ?? []
    grouped[key].push({ index, group })
  })
  return grouped
}

export function filterGroupsByLessonSelection(
  scheduleGroups: Array<Record<string, string | number>> = [],
  args: {
    selectedLessonEvents?: SelectedLessonEvent[]
    selectedGroups?: SelectedGroups
    courseNumber?: string
    academicYear?: number
    semesterCode?: number
  },
): Array<Record<string, string | number>> {
  if (!scheduleGroups.length) return []

  if (args.selectedLessonEvents?.length) {
    const selectedIds = new Set(args.selectedLessonEvents.map((event) => event.eventId))
    const options = extractLessonOptions(
      {
        courseNumber: args.courseNumber ?? '',
        academicYear: args.academicYear ?? 0,
        semesterCode: args.semesterCode ?? 0,
        scheduleGroups: scheduleGroups as CourseOffering['scheduleGroups'],
      },
      args.courseNumber,
    )
    const byId = new Map(options.map((option) => [option.eventId, scheduleGroups[option.index]]))
    return [...selectedIds]
      .map((eventId) => byId.get(eventId))
      .filter((group): group is Record<string, string | number> => group != null)
  }

  if (!args.selectedGroups) return []

  const explicit = ['lecture', 'tutorial', 'lab', 'project'].filter(
    (key) => args.selectedGroups?.[key as keyof SelectedGroups] != null,
  )
  if (!explicit.length) return []

  const grouped = groupScheduleByType(scheduleGroups)
  const selected: Array<Record<string, string | number>> = []

  for (const slotKey of ['lecture', 'tutorial', 'lab', 'project'] as const) {
    const selection = args.selectedGroups[slotKey]
    if (selection == null) continue
    const bucket = grouped[slotKey] ?? []
    if (!bucket.length) continue

    if (typeof selection === 'number' && selection >= 0 && selection < bucket.length) {
      selected.push(bucket[selection].group)
    }
  }

  return selected
}

export function hasLessonSelection(
  selectedLessonEvents?: SelectedLessonEvent[],
  selectedGroups?: SelectedGroups,
): boolean {
  if (selectedLessonEvents?.length) return true
  if (!selectedGroups) return false
  return ['lecture', 'tutorial', 'lab', 'project'].some(
    (key) => selectedGroups[key as keyof SelectedGroups] != null,
  )
}

export function lessonSelectionSummary(
  options: LessonOption[],
  selectedLessonEvents?: SelectedLessonEvent[],
  t?: (key: string) => string,
): string {
  const notSelected = t ? t('planner.lessonNotSelected') : 'not selected'
  const byType = groupLessonOptionsByType(options)
  const selectedByType = new Map<string, LessonOption>()
  for (const event of selectedLessonEvents ?? []) {
    const match = options.find((option) => option.eventId === event.eventId)
    if (match) selectedByType.set(match.type, match)
  }

  const parts: string[] = []
  for (const type of LESSON_TYPE_ORDER) {
    if (!byType[type]?.length) continue
    const selected = selectedByType.get(type)
    if (selected) {
      const time = selected.startTime || selected.timeRange.split('-')[0]?.trim()
      parts.push(`${capitalize(type)}: ${shortDay(selected.day)} ${time}`)
    } else {
      parts.push(`${capitalize(type)}: ${notSelected}`)
    }
  }
  return parts.join(' · ')
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

function shortDay(day: string): string {
  const map: Record<string, string> = {
    Sunday: 'Sun',
    Monday: 'Mon',
    Tuesday: 'Tue',
    Wednesday: 'Wed',
    Thursday: 'Thu',
    Friday: 'Fri',
    Saturday: 'Sat',
    ראשון: 'Sun',
    שני: 'Mon',
    שלישי: 'Tue',
    רביעי: 'Wed',
    חמישי: 'Thu',
    שישי: 'Fri',
    שבת: 'Sat',
  }
  return map[day] ?? day.slice(0, 3)
}

export function selectedEventsFromDraft(
  selectedIds: Set<string>,
  options: LessonOption[],
): SelectedLessonEvent[] {
  return options
    .filter((option) => selectedIds.has(option.eventId))
    .map((option) => ({
      eventId: option.eventId,
      type: option.type,
      group: option.group ?? undefined,
    }))
}

/** Toggle a lesson option using per-type single-selection when multiple groups exist. */
export function toggleLessonSelection(
  current: SelectedLessonEvent[],
  option: LessonOption,
  allOptions: LessonOption[],
): SelectedLessonEvent[] {
  if (current.some((event) => event.eventId === option.eventId)) {
    return current.filter((event) => event.eventId !== option.eventId)
  }

  const sameType = allOptions.filter((item) => item.type === option.type)
  const withoutSameType =
    sameType.length > 1
      ? current.filter((event) => {
          const match = allOptions.find((item) => item.eventId === event.eventId)
          return match?.type !== option.type
        })
      : [...current]

  return [
    ...withoutSameType,
    { eventId: option.eventId, type: option.type, group: option.group ?? undefined },
  ]
}

export function migrateLegacySelectedGroups(
  selectedGroups: SelectedGroups | undefined,
  options: LessonOption[],
): SelectedLessonEvent[] {
  if (!selectedGroups || !options.length) return []
  const byType = groupLessonOptionsByType(options)
  const migrated: SelectedLessonEvent[] = []

  for (const slotKey of ['lecture', 'tutorial', 'lab', 'project'] as const) {
    const selection = selectedGroups[slotKey]
    if (selection == null || typeof selection !== 'number') continue
    const bucket = byType[slotKey] ?? []
    const match = bucket[selection]
    if (match) {
      migrated.push({ eventId: match.eventId, type: match.type, group: match.group ?? undefined })
    }
  }
  return migrated
}
