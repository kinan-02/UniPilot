import { Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { CustomEvent } from '../../types/api'
import { useTranslation } from '../../i18n'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'

const DAY_OPTIONS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

type CustomEventsPanelProps = {
  events: CustomEvent[]
  onChange: (events: CustomEvent[]) => void
  className?: string
}

function newEventId() {
  return `evt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function CustomEventsPanel({ events, onChange, className }: CustomEventsPanelProps) {
  const { t } = useTranslation()
  const [title, setTitle] = useState('')
  const [day, setDay] = useState('Sunday')
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('10:00')

  const addEvent = () => {
    if (!title.trim()) return
    onChange([
      ...events,
      {
        id: newEventId(),
        title: title.trim(),
        day,
        startTime,
        endTime,
      },
    ])
    setTitle('')
  }

  const removeEvent = (id: string) => {
    onChange(events.filter((event) => event.id !== id))
  }

  return (
    <Card className={className}>
      <h3 className="text-sm font-semibold">{t('planner.customEventsTitle')}</h3>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{t('planner.customEventsHint')}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Input label={t('planner.customEventTitle')} value={title} onChange={(e) => setTitle(e.target.value)} />
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t('planner.day')}</span>
          <select
            className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm"
            value={day}
            onChange={(e) => setDay(e.target.value)}
          >
            {DAY_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <Input
          label={t('planner.startTime')}
          type="time"
          value={startTime}
          onChange={(e) => setStartTime(e.target.value)}
        />
        <Input
          label={t('planner.endTime')}
          type="time"
          value={endTime}
          onChange={(e) => setEndTime(e.target.value)}
        />
      </div>

      <Button variant="secondary" size="sm" className="mt-3" onClick={addEvent} disabled={!title.trim()}>
        <Plus className="h-4 w-4" />
        {t('planner.addCustomEvent')}
      </Button>

      <ul className="mt-4 space-y-2">
        {events.length ? (
          events.map((event) => (
            <li
              key={event.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-3 py-2 text-sm"
            >
              <div>
                <p className="font-medium">{event.title}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {event.day} · {event.startTime}–{event.endTime}
                </p>
              </div>
              <Button variant="ghost" size="sm" aria-label={t('common.delete')} onClick={() => removeEvent(event.id!)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))
        ) : (
          <p className="text-sm text-[var(--color-text-muted)]">{t('planner.noCustomEvents')}</p>
        )}
      </ul>
    </Card>
  )
}
