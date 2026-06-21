import { AlertTriangle } from 'lucide-react'
import type { ScheduleGridEvent } from '../../lib/scheduleGridEvents'
import { courseColorStyles } from '../../lib/plannerColors'
import { cn } from '../../lib/utils'

type ScheduleEventBlockProps = {
  event: ScheduleGridEvent
  isHighlighted?: boolean
  hasConflict?: boolean
  onHover?: () => void
  onLeave?: () => void
  onClick?: () => void
}

export function ScheduleEventBlock({
  event,
  isHighlighted,
  hasConflict,
  onHover,
  onLeave,
  onClick,
}: ScheduleEventBlockProps) {
  const isMaybe = event.kind === 'maybe' || event.kind === 'maybe-available'
  const isSelectable =
    event.kind === 'selected' ||
    event.kind === 'available' ||
    event.kind === 'preview' ||
    event.kind === 'maybe' ||
    event.kind === 'maybe-available'

  const colorStyles =
    event.courseNumber && (event.kind === 'selected' || event.kind === 'maybe')
      ? courseColorStyles(event.courseNumber)
      : undefined

  return (
    <div
      role={isSelectable ? 'button' : undefined}
      tabIndex={isSelectable ? 0 : undefined}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      onFocus={onHover}
      onBlur={onLeave}
      onClick={isSelectable ? onClick : undefined}
      onKeyDown={(e) => {
        if (!isSelectable) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onClick?.()
        }
      }}
      className={cn(
        'relative box-border h-full min-h-0 overflow-hidden rounded-sm border px-1.5 py-1 text-start text-[10px] leading-tight shadow-sm transition',
        event.kind === 'selected' && 'z-10 cursor-pointer border-solid',
        event.kind === 'available' &&
          'z-[5] cursor-pointer border-dashed border-[var(--color-border)] bg-white hover:border-[var(--color-primary)]/50',
        event.kind === 'preview' &&
          'z-[15] cursor-pointer border-dashed border-[var(--color-primary)] bg-sky-50 ring-1 ring-[var(--color-primary)]/30',
        event.kind === 'maybe' && 'z-[8] cursor-pointer border-dashed',
        event.kind === 'maybe-available' &&
          'z-[4] cursor-pointer border-dashed border-[var(--color-border)]/80 bg-white/80 hover:border-[var(--color-primary)]/40',
        event.kind === 'custom' && 'z-10 border-[var(--color-text-muted)]/30 bg-[var(--color-surface-muted)]',
        hasConflict && event.kind === 'selected' && 'ring-2 ring-[var(--color-warning)] ring-inset',
        event.previewConflict && 'border-[var(--color-warning)]/70',
        isHighlighted &&
          (event.kind === 'selected' || event.kind === 'maybe') &&
          'ring-2 ring-[var(--color-primary)]',
      )}
      style={
        colorStyles
          ? {
              ...colorStyles,
              ...(isMaybe ? { opacity: 0.82 } : undefined),
              ...(isMaybe
                ? {
                    backgroundImage:
                      'repeating-linear-gradient(-45deg, transparent, transparent 6px, rgba(255,255,255,0.4) 6px, rgba(255,255,255,0.4) 12px)',
                  }
                : undefined),
              ...(hasConflict && event.kind === 'selected'
                ? {
                    backgroundImage:
                      'repeating-linear-gradient(-45deg, transparent, transparent 5px, rgba(234, 88, 12, 0.12) 5px, rgba(234, 88, 12, 0.12) 10px)',
                  }
                : undefined),
            }
          : undefined
      }
    >
      {hasConflict && event.kind === 'selected' ? (
        <span
          className="absolute end-0.5 top-0.5 rounded-sm bg-[var(--color-warning)] p-0.5 text-white shadow-sm"
          aria-hidden
        >
          <AlertTriangle className="h-2.5 w-2.5" />
        </span>
      ) : null}

      {event.courseNumber ? (
        <p className="font-mono font-semibold">{event.courseNumber}</p>
      ) : null}
      <p
        className={cn(
          'font-medium',
          event.kind !== 'selected' && event.kind !== 'maybe' && 'text-[var(--color-text-muted)]',
        )}
      >
        {event.courseTitle}
      </p>
      <p className="text-[var(--color-text-muted)]">
        {event.timeRange}
        {event.slotType ? ` · ${event.slotType}` : ''}
        {event.group ? ` · ${event.group}` : ''}
      </p>
    </div>
  )
}
