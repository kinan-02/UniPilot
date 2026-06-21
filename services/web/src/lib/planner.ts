/** Client-side planner helpers — mirrors backend weekly_schedule logic for previews. */

import type { CustomEvent, WeeklySchedule } from '../types/api'

const TIME_RANGE = /^\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*$/

export function parseTimeRange(timeRange: string): { start: number; end: number } | null {
  const normalized = timeRange.replace(/[–—]/g, '-')
  const match = TIME_RANGE.exec(normalized)
  if (!match) return null
  const start = Number(match[1]) * 60 + Number(match[2])
  const end = Number(match[3]) * 60 + Number(match[4])
  if (end <= start) return null
  return { start, end }
}

export function slotsOverlap(
  left: { day: string; start: number; end: number },
  right: { day: string; start: number; end: number },
): boolean {
  if (left.day !== right.day) return false
  return left.start < right.end && right.start < left.end
}

export function courseNumbersInConflict(schedule?: WeeklySchedule): Set<string> {
  const conflictNumbers = new Set<string>()
  for (const conflict of schedule?.conflicts ?? []) {
    for (const number of conflict.courseNumbers ?? []) {
      conflictNumbers.add(number)
    }
  }
  return conflictNumbers
}

export function formatSlotTypes(types?: string[]): string {
  if (!types?.length) return ''
  return types.join(' · ')
}

export type GridEvent = {
  day: string
  timeRange: string
  slotType?: string
  courseNumber?: string
  courseTitle?: string
  startMinutes: number
  endMinutes: number
}

const DAY_ORDER = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת', 'Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

export function daySortKey(day: string): number {
  const index = DAY_ORDER.indexOf(day)
  return index >= 0 ? index : 99
}

export function eventsFromSchedule(schedule?: WeeklySchedule): GridEvent[] {
  const events: GridEvent[] = []
  for (const dayBlock of schedule?.weekView ?? []) {
    for (const slot of dayBlock.slots) {
      const parsed = parseTimeRange(slot.timeRange)
      if (!parsed) continue
      events.push({
        day: dayBlock.day,
        timeRange: slot.timeRange,
        slotType: slot.slotType,
        courseNumber: slot.courseNumber,
        courseTitle: slot.courseTitle,
        startMinutes: parsed.start,
        endMinutes: parsed.end,
      })
    }
  }
  return events.sort((a, b) => daySortKey(a.day) - daySortKey(b.day) || a.startMinutes - b.startMinutes)
}

export function gridTimeBounds(events: GridEvent[]): { min: number; max: number } {
  if (!events.length) return { min: 8 * 60, max: 20 * 60 }
  const starts = events.map((event) => event.startMinutes)
  const ends = events.map((event) => event.endMinutes)
  const min = Math.floor(Math.min(...starts) / 60) * 60
  const max = Math.ceil(Math.max(...ends) / 60) * 60
  return { min: Math.max(min, 8 * 60), max: Math.min(Math.max(max, min + 120), 22 * 60) }
}

export function formatMinutes(total: number): string {
  const hours = Math.floor(total / 60)
  const minutes = total % 60
  return `${hours}:${String(minutes).padStart(2, '0')}`
}

export function eventsFromCustomBlocks(customEvents: CustomEvent[] = []): GridEvent[] {
  return customEvents
    .map((block) => {
      const startParts = block.startTime.split(':').map(Number)
      const endParts = block.endTime.split(':').map(Number)
      if (startParts.length < 2 || endParts.length < 2) return null
      const startMinutes = startParts[0] * 60 + startParts[1]
      const endMinutes = endParts[0] * 60 + endParts[1]
      if (endMinutes <= startMinutes) return null
      return {
        day: block.day,
        timeRange: `${block.startTime}-${block.endTime}`,
        slotType: 'personal',
        courseNumber: '●',
        courseTitle: block.title,
        startMinutes,
        endMinutes,
      }
    })
    .filter((event): event is GridEvent => event != null)
}
