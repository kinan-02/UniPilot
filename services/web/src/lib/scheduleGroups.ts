/** Client-side schedule group parsing for group selection UI. */

import type { SelectedGroups } from '../types/api'

const SLOT_ALIASES: Record<string, string[]> = {
  lecture: ['lecture', 'הרצאה', 'lec'],
  tutorial: ['tutorial', 'תרגול', 'recitation', 'lesson', 'תר'],
  lab: ['lab', 'מעבדה', 'laboratory'],
  project: ['project', 'פרויקט', 'workshop', 'סדנה'],
}

export type GroupOption = {
  slotKey: string
  index: number
  label: string
  day: string
  timeRange: string
}

function normalizeGroup(group: Record<string, string>) {
  return {
    day: group.day || group.יום || '',
    timeRange: group.time || group.שעה || '',
    slotType: group.type || group.סוג || '',
  }
}

function canonicalSlotType(slotType: string): string {
  const normalized = slotType.trim().toLowerCase()
  if (!normalized) return 'other'
  for (const [canonical, aliases] of Object.entries(SLOT_ALIASES)) {
    if (aliases.some((alias) => normalized.includes(alias.toLowerCase()))) return canonical
  }
  return normalized
}

export function groupOptionsFromOffering(
  scheduleGroups: Array<Record<string, string>> = [],
): GroupOption[] {
  const buckets: Record<string, Array<Record<string, string>>> = {}

  for (const group of scheduleGroups) {
    const normalized = normalizeGroup(group)
    const key = canonicalSlotType(normalized.slotType)
    buckets[key] = buckets[key] ?? []
    buckets[key].push(group)
  }

  const options: GroupOption[] = []
  for (const [slotKey, groups] of Object.entries(buckets)) {
    groups.forEach((group, index) => {
      const normalized = normalizeGroup(group)
      options.push({
        slotKey,
        index,
        label: normalized.slotType || slotKey,
        day: normalized.day,
        timeRange: normalized.timeRange,
      })
    })
  }
  return options
}

export function selectedGroupsSummary(
  selected?: SelectedGroups,
  options: GroupOption[] = [],
): string {
  if (!selected || !options.length) return ''
  const parts: string[] = []
  for (const slotKey of ['lecture', 'tutorial', 'lab', 'project'] as const) {
    const value = selected[slotKey]
    if (value == null) continue
    const match = options.find((opt) => opt.slotKey === slotKey && opt.index === value)
    if (match) parts.push(`${match.label}: ${match.day} ${match.timeRange}`)
  }
  return parts.join(' · ')
}

export function hasPartialGroupSelection(selected?: SelectedGroups): boolean {
  if (!selected) return false
  return ['lecture', 'tutorial', 'lab', 'project'].some(
    (key) => selected[key as keyof SelectedGroups] != null,
  )
}

export function buildSelectedGroupsFromOptions(
  current: SelectedGroups | undefined,
  slotKey: string,
  index: number | null,
): SelectedGroups {
  return {
    lecture: current?.lecture ?? null,
    tutorial: current?.tutorial ?? null,
    lab: current?.lab ?? null,
    project: current?.project ?? null,
    [slotKey]: index,
  }
}
