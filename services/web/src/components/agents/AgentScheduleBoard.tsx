import { Clock, LayoutGrid, List } from 'lucide-react'
import { useState } from 'react'
import { WeeklyScheduleGrid } from '../plans/WeeklyScheduleGrid'
import { masCoursesToGridEvents } from '../../lib/masScheduleGrid'
import { cn } from '../../lib/utils'
import { AgentSection } from './AgentSection'
import type { MasScheduleCourse } from '../../types/api'

type AgentScheduleBoardProps = {
  courses: MasScheduleCourse[]
  title: string
  noSlotsLabel: string
  gridViewLabel: string
  listViewLabel: string
}

const DAY_ORDER = [
  'ראשון',
  'שני',
  'שלישי',
  'רביעי',
  'חמישי',
  'שישי',
  'שבת',
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
]

function daySortIndex(day: string): number {
  const index = DAY_ORDER.findIndex((entry) => day.includes(entry) || entry.includes(day))
  return index >= 0 ? index : 99
}

export function AgentScheduleBoard({
  courses,
  title,
  noSlotsLabel,
  gridViewLabel,
  listViewLabel,
}: AgentScheduleBoardProps) {
  const [view, setView] = useState<'grid' | 'list'>('grid')
  if (courses.length === 0) return null

  const gridEvents = masCoursesToGridEvents(courses)
  const hasGrid = gridEvents.length > 0

  return (
    <AgentSection title={title}>
      {hasGrid ? (
        <div className="mb-4 inline-flex rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 p-1">
          <button
            type="button"
            onClick={() => setView('grid')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition',
              view === 'grid'
                ? 'bg-white text-[var(--color-text)] shadow-sm'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]',
            )}
          >
            <LayoutGrid className="h-3.5 w-3.5" aria-hidden />
            {gridViewLabel}
          </button>
          <button
            type="button"
            onClick={() => setView('list')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition',
              view === 'list'
                ? 'bg-white text-[var(--color-text)] shadow-sm'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]',
            )}
          >
            <List className="h-3.5 w-3.5" aria-hidden />
            {listViewLabel}
          </button>
        </div>
      ) : null}

      {view === 'grid' && hasGrid ? (
        <WeeklyScheduleGrid
          lessonEvents={gridEvents}
          showEmptyGrid={false}
          emptyMessage={noSlotsLabel}
        />
      ) : (
        <div className="space-y-3">
          {courses.map((course) => {
            const sortedSlots = [...course.slots].sort(
              (a, b) => daySortIndex(a.day) - daySortIndex(b.day),
            )
            return (
              <div
                key={course.courseId}
                className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/20"
              >
                <div className="border-b border-[var(--color-border)] bg-white px-4 py-3">
                  <p className="font-medium">
                    <span className="font-mono text-[var(--color-primary)]">{course.courseId}</span>
                    <span className="mx-2 text-[var(--color-text-muted)]">·</span>
                    {course.title}
                  </p>
                </div>
                {sortedSlots.length > 0 ? (
                  <ul className="divide-y divide-[var(--color-border)]">
                    {sortedSlots.map((slot, index) => (
                      <li
                        key={`${slot.day}-${slot.timeRange}-${index}`}
                        className="flex items-center gap-3 px-4 py-2.5 text-sm"
                      >
                        <span className="w-20 shrink-0 font-medium text-[var(--color-text)]">
                          {slot.day}
                        </span>
                        <Clock className="h-3.5 w-3.5 text-[var(--color-text-muted)]" aria-hidden />
                        <span className="text-[var(--color-text-muted)]">{slot.timeRange}</span>
                        {slot.slotType ? (
                          <span className="ms-auto rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-600">
                            {slot.slotType}
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="px-4 py-3 text-xs text-[var(--color-text-muted)]">{noSlotsLabel}</p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </AgentSection>
  )
}
