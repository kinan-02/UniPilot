/** Generate ICS calendar export for semester plan (Asia/Jerusalem). */

import type { CustomEvent, ExamSummary, WeeklySchedule } from '../types/api'
import { eventsFromSchedule, scheduleIncludesCustomBlocks } from './planner'

const TZ = 'Asia/Jerusalem'
const DAY_TO_DOW: Record<string, number> = {
  Sunday: 0,
  Monday: 1,
  Tuesday: 2,
  Wednesday: 3,
  Thursday: 4,
  Friday: 5,
  Saturday: 6,
  ראשון: 0,
  שני: 1,
  שלישי: 2,
  רביעי: 3,
  חמישי: 4,
  שישי: 5,
  שבת: 6,
}

function pad(n: number) {
  return String(n).padStart(2, '0')
}

function formatIcsUtc(date: Date) {
  return (
    `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}` +
    `T${pad(date.getUTCHours())}${pad(date.getUTCMinutes())}${pad(date.getUTCSeconds())}Z`
  )
}

function nextDateForDay(dayName: string, hour: number, minute: number): Date {
  const target = DAY_TO_DOW[dayName.trim()]
  if (target == null) return new Date()
  const now = new Date()
  const date = new Date(now)
  date.setHours(hour, minute, 0, 0)
  const diff = (target - date.getDay() + 7) % 7
  date.setDate(date.getDate() + diff)
  return date
}

function escapeIcs(text: string) {
  return text.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n')
}

type IcsOptions = {
  planName: string
  schedule?: WeeklySchedule
  examSummary?: ExamSummary
  customEvents?: CustomEvent[]
  customEventsDirty?: boolean
}

export function generatePlanIcs({
  planName,
  schedule,
  examSummary,
  customEvents = [],
  customEventsDirty = false,
}: IcsOptions): string {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//UniPilot//Semester Planner//EN',
    'CALSCALE:GREGORIAN',
    'X-WR-CALNAME:' + escapeIcs(planName),
    'X-WR-TIMEZONE:' + TZ,
    'BEGIN:VTIMEZONE',
    'TZID:Asia/Jerusalem',
    'X-LIC-LOCATION:Asia/Jerusalem',
    'BEGIN:STANDARD',
    'TZOFFSETFROM:+0300',
    'TZOFFSETTO:+0200',
    'END:STANDARD',
    'BEGIN:DAYLIGHT',
    'TZOFFSETFROM:+0200',
    'TZOFFSETTO:+0300',
    'END:DAYLIGHT',
    'END:VTIMEZONE',
  ]

  let uid = 0
  const addEvent = (summary: string, start: Date, end: Date, description?: string) => {
    uid += 1
    lines.push('BEGIN:VEVENT')
    lines.push(`UID:unipilot-${uid}@unipilot.local`)
    lines.push(`DTSTAMP:${formatIcsUtc(new Date())}`)
    lines.push(`DTSTART:${formatIcsUtc(start)}`)
    lines.push(`DTEND:${formatIcsUtc(end)}`)
    lines.push(`SUMMARY:${escapeIcs(summary)}`)
    if (description) lines.push(`DESCRIPTION:${escapeIcs(description)}`)
    lines.push('END:VEVENT')
  }

  for (const event of eventsFromSchedule(schedule)) {
    if (
      customEventsDirty &&
      (event.courseNumber === 'CUSTOM' || event.slotType === 'custom' || event.slotType === 'personal')
    ) {
      continue
    }
    const startHour = Math.floor(event.startMinutes / 60)
    const startMin = event.startMinutes % 60
    const endHour = Math.floor(event.endMinutes / 60)
    const endMin = event.endMinutes % 60
    const start = nextDateForDay(event.day, startHour, startMin)
    const end = nextDateForDay(event.day, endHour, endMin)
    addEvent(
      `${event.courseNumber} ${event.courseTitle ?? ''}`.trim(),
      start,
      end,
      'Weekly class slot (single-week export; adjust dates as needed)',
    )
  }

  for (const exam of examSummary?.exams ?? []) {
    if (!exam.date || exam.isMissing) continue
    const [year, month, day] = exam.date.split('-').map(Number)
    const [hour, minute] = (exam.startTime ?? '09:00').split(':').map(Number)
    const start = new Date(Date.UTC(year, month - 1, day, hour - 2, minute))
    const end = new Date(start.getTime() + 3 * 60 * 60 * 1000)
    addEvent(
      `Exam ${exam.courseNumber} Moed ${exam.moed ?? ''}`.trim(),
      start,
      end,
      exam.courseName,
    )
  }

  const includeSeparateCustom =
    customEventsDirty || !scheduleIncludesCustomBlocks(schedule)
  if (includeSeparateCustom) {
    for (const block of customEvents) {
      const [sh, sm] = block.startTime.split(':').map(Number)
      const [eh, em] = block.endTime.split(':').map(Number)
      const start = nextDateForDay(block.day, sh, sm)
      const end = nextDateForDay(block.day, eh, em)
      addEvent(block.title, start, end, block.notes)
    }
  }

  lines.push('END:VCALENDAR')
  return lines.join('\r\n')
}

export function downloadIcs(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/calendar;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}
