import { Fragment } from 'react'
import { AlertTriangle } from 'lucide-react'
import type { CustomEvent, WeeklySchedule } from '../../types/api'
import type { GridEvent } from '../../lib/planner'
import type { ScheduleGridEvent } from '../../lib/scheduleGridEvents'
import { useTranslation } from '../../i18n'
import {
  conflictsToGridBounds,
  eventsFromSchedule,
  formatMinutes,
  gridTimeBounds,
  weekGridDays,
} from '../../lib/planner'
import { courseColor } from '../../lib/plannerColors'
import { cn } from '../../lib/utils'
import { ScheduleEventBlock } from './ScheduleEventBlock'

type WeeklyScheduleGridProps = {
  schedule?: WeeklySchedule
  lessonEvents?: ScheduleGridEvent[]
  searchPreviewEvents?: GridEvent[]
  customEvents?: CustomEvent[]
  highlightedCourseNumber?: string | null
  highlightedCourseNumbers?: Set<string>
  conflictCourseNumbers?: Set<string>
  onLessonHover?: (eventId: string | null, courseNumber: string | null) => void
  onLessonClick?: (eventId: string, courseNumber: string) => void
  onConflictHover?: (courseNumbers: string[] | null) => void
  emptyMessage?: string
  showEmptyGrid?: boolean
  className?: string
}

const GRID_STEP = 30

export function WeeklyScheduleGrid({
  schedule,
  lessonEvents = [],
  searchPreviewEvents = [],
  highlightedCourseNumber,
  highlightedCourseNumbers,
  conflictCourseNumbers,
  onLessonHover,
  onLessonClick,
  onConflictHover,
  emptyMessage,
  showEmptyGrid = false,
  className,
}: WeeklyScheduleGridProps) {
  const { t, locale } = useTranslation()
  const scheduleEvents: ScheduleGridEvent[] =
    lessonEvents.length > 0
      ? lessonEvents
      : eventsFromSchedule(schedule).map((event) => ({ ...event, kind: 'selected' as const }))
  const allRenderableEvents = [
    ...scheduleEvents,
    ...searchPreviewEvents.map((event) => ({
      ...event,
      kind: 'preview' as const,
    })),
  ]
  const hasEvents = allRenderableEvents.length > 0
  const conflicts = schedule?.conflicts ?? []
  const conflictBounds = conflictsToGridBounds(conflicts)

  if (!hasEvents && !showEmptyGrid) {
    return (
      <p className={cn('text-sm text-[var(--color-text-muted)]', className)}>
        {emptyMessage ?? t('plans.scheduleEmpty')}
      </p>
    )
  }

  const isRtl = locale === 'he'
  const eventDays = [
    ...allRenderableEvents.map((event) => event.day),
    ...conflictBounds.map((bound) => bound.day),
  ]
  const days = weekGridDays(locale, eventDays)
  const { min, max } = hasEvents ? gridTimeBounds(allRenderableEvents) : { min: 8 * 60, max: 20 * 60 }
  const rowCount = Math.ceil((max - min) / GRID_STEP)

  const isCourseHighlighted = (courseNumber?: string) =>
    Boolean(
      courseNumber &&
        (highlightedCourseNumber === courseNumber || highlightedCourseNumbers?.has(courseNumber)),
    )

  return (
    <div className={cn('space-y-3', className)} data-testid="weekly-schedule-grid">
      {conflicts.length ? (
        <div className="rounded-xl border border-[var(--color-warning)]/40 bg-amber-50/80 p-3">
          <p className="mb-2 text-xs font-semibold text-[var(--color-warning)]">
            {t('planner.scheduleConflictHint')}
          </p>
          <div className="flex flex-wrap gap-2">
            {conflicts.map((conflict, index) => {
              const numbers = conflict.courseNumbers ?? []
              return (
                <button
                  key={`${conflict.day}-${conflict.timeRange}-${index}`}
                  type="button"
                  onMouseEnter={() => onConflictHover?.(numbers)}
                  onMouseLeave={() => onConflictHover?.(null)}
                  onFocus={() => onConflictHover?.(numbers)}
                  onBlur={() => onConflictHover?.(null)}
                  className="inline-flex max-w-full items-center gap-2 rounded-lg border border-[var(--color-warning)]/50 bg-white px-2.5 py-1.5 text-start text-xs shadow-sm transition hover:border-[var(--color-warning)] hover:bg-amber-50"
                >
                  <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-[var(--color-warning)]" aria-hidden />
                  <span className="font-medium text-[var(--color-text)]">
                    {conflict.day} {conflict.timeRange}
                  </span>
                  <span className="flex flex-wrap items-center gap-1 text-[var(--color-text-muted)]">
                    {numbers.map((number, numberIndex) => (
                      <Fragment key={number}>
                        {numberIndex > 0 ? <span aria-hidden>↔</span> : null}
                        <span
                          className="rounded px-1 py-0.5 font-mono text-[10px] font-semibold"
                          style={{
                            backgroundColor: `${courseColor(number)}22`,
                            borderColor: courseColor(number),
                            borderWidth: 1,
                            borderStyle: 'solid',
                          }}
                        >
                          {number}
                        </span>
                      </Fragment>
                    ))}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      ) : null}

      <div className="relative w-full overflow-x-auto rounded-xl border border-[var(--color-border)]">
        {!hasEvents && emptyMessage ? (
          <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-white/70 p-6">
            <p className="max-w-sm text-center text-sm text-[var(--color-text-muted)]">{emptyMessage}</p>
          </div>
        ) : null}

        <div
          dir={isRtl ? 'rtl' : 'ltr'}
          className="grid w-full min-w-full"
          style={{
            gridTemplateColumns: `52px repeat(${days.length}, minmax(0, 1fr))`,
            gridTemplateRows: `36px repeat(${rowCount}, 28px)`,
          }}
        >
          <div
            style={{ gridColumn: 1, gridRow: 1 }}
            className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]"
          />
          {days.map((day, dayIndex) => (
            <div
              key={day}
              style={{ gridColumn: dayIndex + 2, gridRow: 1 }}
              className="border-b border-s border-[var(--color-border)] bg-[var(--color-surface-muted)] px-2 py-2 text-center text-xs font-semibold"
            >
              {day}
            </div>
          ))}

          {Array.from({ length: rowCount }, (_, rowIndex) => {
            const minuteMark = min + rowIndex * GRID_STEP
            const gridRow = rowIndex + 2
            return (
              <Fragment key={`time-${minuteMark}`}>
                <div
                  dir="ltr"
                  style={{ gridColumn: 1, gridRow }}
                  className={cn(
                    'border-b border-[var(--color-border)] px-1 text-[10px] leading-6 tabular-nums text-[var(--color-text-muted)]',
                    isRtl ? 'text-left' : 'text-right',
                  )}
                >
                  {rowIndex % 2 === 0 ? formatMinutes(minuteMark) : ''}
                </div>
                {days.map((day, dayIndex) => (
                  <div
                    key={`${day}-${minuteMark}`}
                    style={{ gridColumn: dayIndex + 2, gridRow }}
                    className="border-b border-s border-[var(--color-border)] bg-white"
                  />
                ))}
              </Fragment>
            )
          })}

          {conflictBounds.map((bound, index) => {
            const dayIndex = days.indexOf(bound.day)
            if (dayIndex < 0) return null
            const startRow = Math.floor((bound.startMinutes - min) / GRID_STEP) + 2
            const span = Math.max(1, Math.ceil((bound.endMinutes - bound.startMinutes) / GRID_STEP))

            return (
              <div
                key={`conflict-${bound.day}-${bound.startMinutes}-${index}`}
                className="pointer-events-none z-[8] min-h-0 rounded-sm border-2 border-dashed border-[var(--color-warning)]/70 bg-[var(--color-warning)]/10"
                style={{
                  gridColumn: dayIndex + 2,
                  gridRow: `${startRow} / span ${span}`,
                  backgroundImage:
                    'repeating-linear-gradient(-45deg, transparent, transparent 6px, rgba(234, 88, 12, 0.08) 6px, rgba(234, 88, 12, 0.08) 12px)',
                }}
              />
            )
          })}

          {allRenderableEvents.map((event, index) => {
            const dayIndex = days.indexOf(event.day)
            if (dayIndex < 0) return null
            const startRow = Math.floor((event.startMinutes - min) / GRID_STEP) + 2
            const span = Math.max(1, Math.ceil((event.endMinutes - event.startMinutes) / GRID_STEP))
            const hasConflict = Boolean(
              event.courseNumber &&
                event.kind === 'selected' &&
                conflictCourseNumbers?.has(event.courseNumber),
            )
            const isHighlighted = isCourseHighlighted(event.courseNumber)
            const eventId = 'eventId' in event ? event.eventId : undefined
            const courseNumber = event.courseNumber

            return (
              <div
                key={`${eventId ?? event.courseNumber}-${event.day}-${event.timeRange}-${index}`}
                className="z-20 min-h-0"
                style={{
                  gridColumn: dayIndex + 2,
                  gridRow: `${startRow} / span ${span}`,
                }}
              >
                <ScheduleEventBlock
                  event={event as ScheduleGridEvent}
                  isHighlighted={isHighlighted}
                  hasConflict={hasConflict}
                  onHover={() => {
                    if (eventId && courseNumber) onLessonHover?.(eventId, courseNumber)
                  }}
                  onLeave={() => onLessonHover?.(null, null)}
                  onClick={() => {
                    if (eventId && courseNumber && onLessonClick) onLessonClick(eventId, courseNumber)
                  }}
                />
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
