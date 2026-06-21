import { describe, expect, it, vi, beforeEach, type ComponentProps } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { I18nProvider } from '../../i18n'
import { SelectedCourseListItem } from './SelectedCourseListItem'
import type { DraftCourse } from '../../types/planner'

const course: DraftCourse = {
  courseId: 'c1',
  courseNumber: '02340117',
  courseTitle: 'Algorithms',
  credits: 4,
  isActive: true,
}

function renderItem(props: Partial<ComponentProps<typeof SelectedCourseListItem>> = {}) {
  const onMoveToOtherList = vi.fn()
  const onRemove = vi.fn()

  render(
    <I18nProvider>
      <SelectedCourseListItem
        course={course}
        onMoveToOtherList={onMoveToOtherList}
        onRemove={onRemove}
        {...props}
      />
    </I18nProvider>,
  )

  return { onMoveToOtherList, onRemove }
}

describe('SelectedCourseListItem list moves', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
  })
  it('shows move-to-maybe control on selected variant', async () => {
    const user = userEvent.setup()
    const { onMoveToOtherList } = renderItem({ variant: 'selected' })
    await user.click(screen.getByRole('button', { name: /Move to maybe/i }))
    expect(onMoveToOtherList).toHaveBeenCalledTimes(1)
  })

  it('shows move-to-selected control on maybe variant', async () => {
    const user = userEvent.setup()
    const { onMoveToOtherList } = renderItem({ variant: 'maybe' })
    await user.click(screen.getByRole('button', { name: /Move to selected/i }))
    expect(onMoveToOtherList).toHaveBeenCalledTimes(1)
  })

  it('removes course when remove button is clicked', async () => {
    const user = userEvent.setup()
    const { onRemove } = renderItem({ variant: 'maybe' })
    await user.click(screen.getByRole('button', { name: /Remove course/i }))
    expect(onRemove).toHaveBeenCalledTimes(1)
  })
})
