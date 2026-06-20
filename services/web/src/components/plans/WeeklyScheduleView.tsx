import type { WeeklySchedule } from '../../types/api'
import { useTranslation } from '../../i18n'
import { cn } from '../../lib/utils'
import { Badge } from '../ui/Card'

type WeeklyScheduleViewProps = {
  schedule?: WeeklySchedule
  className?: string
}

export function WeeklyScheduleView({ schedule, className }: WeeklyScheduleViewProps) {
  const { t } = useTranslation()

  if (!schedule?.weekView?.length) {
    return (
      <p className={cn('text-sm text-[var(--color-text-muted)]', className)}>
        {t('plans.scheduleEmpty')}
      </p>
    )
  }

  const statusTone =
    schedule.status === 'valid'
      ? 'success'
      : schedule.status === 'conflicts'
        ? 'warning'
        : 'neutral'

  return (
    <div className={cn('space-y-4', className)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={statusTone}>{schedule.summary ?? schedule.status}</Badge>
        {schedule.status === 'conflicts' ? (
          <span className="text-sm text-[var(--color-warning)]">{t('plans.scheduleConflicts')}</span>
        ) : schedule.status === 'valid' ? (
          <span className="text-sm text-[var(--color-success)]">{t('plans.scheduleValid')}</span>
        ) : null}
      </div>

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {schedule.weekView.map((dayBlock) => (
          <div
            key={dayBlock.day}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4"
          >
            <p className="mb-3 text-sm font-semibold">{dayBlock.day}</p>
            <div className="space-y-2">
              {dayBlock.slots.map((slot, index) => (
                <div
                  key={`${slot.timeRange}-${slot.courseNumber}-${index}`}
                  className="rounded-lg bg-white px-3 py-2 text-sm shadow-sm"
                >
                  <p className="font-mono text-xs text-[var(--color-primary)]">{slot.courseNumber}</p>
                  <p className="font-medium">{slot.courseTitle}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {slot.timeRange}
                    {slot.slotType ? ` · ${slot.slotType}` : ''}
                  </p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {schedule.conflicts?.length ? (
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
