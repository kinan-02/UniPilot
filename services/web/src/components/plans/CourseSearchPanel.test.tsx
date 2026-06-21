import { describe, expect, it, vi, beforeEach, type ComponentProps } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { I18nProvider } from '../../i18n'
import { CourseSearchPanel } from './CourseSearchPanel'
import type { CourseSummary } from '../../types/api'

const sampleCourse: CourseSummary = {
  id: 'course-1',
  courseNumber: '02340117',
  courseTitle: 'Intro to CS',
  credits: 4,
  faculty: 'CS',
}

function renderPanel(props: Partial<ComponentProps<typeof CourseSearchPanel>> = {}) {
  const onAdd = vi.fn()
  const onAddMaybe = vi.fn()
  const onInfo = vi.fn()

  render(
    <I18nProvider>
      <CourseSearchPanel
        locale="en"
        searchMinLength={2}
        debouncedSearch="02340117"
        loading={false}
        error={false}
        items={[sampleCourse]}
        selectedCourseNumbers={new Set()}
        maybeCourseNumbers={new Set()}
        onAdd={onAdd}
        onAddMaybe={onAddMaybe}
        onInfo={onInfo}
        {...props}
      />
    </I18nProvider>,
  )

  return { onAdd, onAddMaybe, onInfo }
}

describe('CourseSearchPanel maybe integration', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
  })
  it('shows add-to-plan and add-to-maybe actions for new courses', () => {
    renderPanel()
    expect(screen.getByRole('button', { name: /Add to maybe/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /Add to plan/i })).toBeEnabled()
  })

  it('calls onAddMaybe when maybe button is clicked', async () => {
    const user = userEvent.setup()
    const { onAddMaybe } = renderPanel()
    await user.click(screen.getByRole('button', { name: /Add to maybe/i }))
    expect(onAddMaybe).toHaveBeenCalledWith(sampleCourse)
  })

  it('disables both actions when course is already selected', () => {
    renderPanel({ selectedCourseNumbers: new Set(['02340117']) })
    expect(screen.getByText(/Already selected/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add to maybe/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Add to plan/i })).toBeDisabled()
  })

  it('disables both actions when course is already in maybe list', () => {
    renderPanel({ maybeCourseNumbers: new Set(['02340117']) })
    expect(screen.getByText(/In maybe list/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Add to maybe/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Add to plan/i })).toBeDisabled()
  })
})
