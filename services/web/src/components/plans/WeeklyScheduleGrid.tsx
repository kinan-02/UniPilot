import type { CustomEvent, WeeklySchedule } from '../../types/api'
import type { GridEvent } from '../../lib/planner'
import { useTranslation } from '../../i18n'
import {
  daySortKey,
  eventsFromCustomBlocks,
  eventsFromSchedule,
  formatMinutes,
  gridTimeBounds,
} from '../../lib/planner'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/Card'

type WeeklyScheduleGridProps = {
  schedule?: WeeklySchedule
  previewEvents?: GridEvent[]
  customEvents?: CustomEvent[]
  className?: string
}

const GRID_STEP = 30

export function WeeklyScheduleGrid({
  schedule,
  previewEvents = [],
  customEvents = [],
  className,
}: WeeklyScheduleGridProps) {
  const { t } = useTranslation()
  const events = [
    ...eventsFromSchedule(schedule),
    ...eventsFromCustomBlocks(customEvents.length ? customEvents : schedule?.customEvents),
    ...previewEvents,
  ]

  if (!events.length) {
    return (
      <p className={cn('text-sm text-[var(--color-text-muted)]', className)}>
        {t('plans.scheduleEmpty')}
      </p>
    )
  }

  const days = [...new Set(events.map((event) => event.day))].sort(
    (a, b) => daySortKey(a) - daySortKey(b),
  )
  const { min, max } = gridTimeBounds(events)
  const totalMinutes = max - min
  const rowCount = Math.ceil(totalMinutes / GRID_STEP)

  const statusTone =
    schedule?.status === 'valid'
      ? 'success'
      : schedule?.status === 'conflicts'
        ? 'warning'
        : 'neutral'

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={statusTone}>{schedule?.summary ?? schedule?.status}</Badge>
        {schedule?.status === 'conflicts' ? (
          <span className="text-sm text-[var(--color-warning)]">{t('plans.scheduleConflicts')}</span>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)]">
        <div
          className="grid min-w-[640px]"
          style={{
            gridTemplateColumns: `56px repeat(${days.length}, minmax(100px, 1fr))`,
            gridTemplateRows: `32px repeat(${rowCount}, 24px)`,
          }}
        >
          <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]" />
          {days.map((day) => (
            <div
              key={day}
              className="border-b border-s border-[var(--color-border)] bg-[var(--color-surface-muted)] px-2 py-2 text-center text-xs font-semibold"
            >
              {day}
            </div>
          ))}

          {Array.from({ length: rowCount }, (_, rowIndex) => {
            const minuteMark = min + rowIndex * GRID_STEP
            return (
              <div key={`time-${minuteMark}`} className="contents">
                <div className="border-b border-[var(--color-border)] pe-1 text-end text-[10px] leading-6 text-[var(--color-text-muted)]">
                  {rowIndex % 2 === 0 ? formatMinutes(minuteMark) : ''}
                </div>
                {days.map((day) => (
                  <div
                    key={`${day}-${minuteMark}`}
                    className="border-b border-s border-[var(--color-border)] bg-white/50"
                  />
                ))}
              </div>
            )
          })}

          {events.map((event, index) => {
            const dayIndex = days.indexOf(event.day)
            if (dayIndex < 0) return null
            const isPreview = previewEvents.some(
              (preview) =>
                preview.courseNumber === event.courseNumber &&
                preview.timeRange === event.timeRange,
            )
            const startRow = Math.floor((event.startMinutes - min) / GRID_STEP) + 2
            const span = Math.max(1, Math.ceil((event.endMinutes - event.startMinutes) / GRID_STEP))
            return (
              <div
                key={`${event.courseNumber}-${event.timeRange}-${index}`}
                className={cn(
                  'z-10 m-0.5 overflow-hidden rounded-md border px-1 py-0.5 text-[10px] leading-tight',
                  isPreview
                    ? 'border-dashed border-[var(--color-primary)] bg-[var(--color-primary)]/5 opacity-80'
                    : event.slotType === 'personal'
                      ? 'border-[var(--color-text-muted)]/30 bg-[var(--color-surface-muted)]'
                      : 'border-[var(--color-primary)]/20 bg-[var(--color-primary)]/10',
                )}
                style={{
                  gridColumn: dayIndex + 2,
                  gridRow: `${startRow} / span ${span}`,
                }}
              >
                <p className="font-mono text-[var(--color-primary)]">{event.courseNumber}</p>
                <p className="truncate font-medium">{event.courseTitle}</p>
                <p className="text-[var(--color-text-muted)]">
                  {event.timeRange}
                  {event.slotType ? ` · ${event.slotType}` : ''}
                </p>
              </div>
            )
          })}
        </div>
      </div>

      {schedule?.conflicts?.length ? (
        <div className="rounded-xl border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5 p-4">
          <p className="text-sm font-medium text-[var(--color-warning)]">{t('plans.scheduleConflicts')}</p>
          <ul className="mt-2 space-y-1 text-sm text-[var(--color-text-muted)]">
            {schedule.conflicts.map((conflict, index) => (
              <li key={index}>
                {conflict.day} {conflict.timeRange}: {conflict.courseNumbers?.join(' ↔ ')}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
