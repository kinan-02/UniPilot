import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ScheduleEventBlock } from './ScheduleEventBlock'
import type { ScheduleGridEvent } from '../../lib/scheduleGridEvents'

const baseEvent: ScheduleGridEvent = {
  day: 'Sunday',
  timeRange: '08:30-10:30',
  slotType: 'Lecture',
  courseNumber: '02340117',
  courseTitle: 'Algorithms',
  startMinutes: 510,
  endMinutes: 630,
  kind: 'maybe',
  eventId: 'ev-1',
}

describe('ScheduleEventBlock maybe styling', () => {
  it('renders maybe events as interactive blocks', async () => {
    const user = userEvent.setup()
    const onClick = vi.fn()
    render(<ScheduleEventBlock event={baseEvent} onClick={onClick} />)

    const block = screen.getByRole('button')
    expect(block).toHaveTextContent('02340117')
    await user.click(block)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('renders maybe-available events as interactive', () => {
    render(
      <ScheduleEventBlock
        event={{ ...baseEvent, kind: 'maybe-available' }}
        previewConflict
      />,
    )
    expect(screen.getByRole('button')).toBeInTheDocument()
  })
})
