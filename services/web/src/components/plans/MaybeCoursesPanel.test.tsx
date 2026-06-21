import { describe, expect, it, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { I18nProvider } from '../../i18n'
import { MaybeCoursesPanel } from './MaybeCoursesPanel'
import { SelectedCourseListItem } from './SelectedCourseListItem'
import type { DraftCourse } from '../../types/planner'

const course: DraftCourse = {
  courseId: 'm1',
  courseNumber: '02340114',
  courseTitle: 'Maybe course',
  credits: 3,
  isActive: true,
}

describe('MaybeCoursesPanel', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'en')
  })
  it('shows empty state when there are no maybe courses', () => {
    render(
      <I18nProvider>
        <MaybeCoursesPanel courseCount={0}>{null}</MaybeCoursesPanel>
      </I18nProvider>,
    )
    expect(screen.getByRole('heading', { name: /Maybe courses/i })).toBeInTheDocument()
    expect(screen.getByText(/No maybe courses yet/i)).toBeInTheDocument()
  })

  it('renders maybe course children when list is populated', () => {
    render(
      <I18nProvider>
        <MaybeCoursesPanel courseCount={1}>
          <SelectedCourseListItem course={course} variant="maybe" />
        </MaybeCoursesPanel>
      </I18nProvider>,
    )
    expect(screen.getByText('02340114')).toBeInTheDocument()
    expect(screen.getByText('Maybe course')).toBeInTheDocument()
  })
})
