import type { ComponentProps } from 'react'
import { describe, expect, it, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { I18nProvider } from '../../i18n'
import { PlannerAutoAssistPanel } from './PlannerAutoAssistPanel'

function renderPanel(props: ComponentProps<typeof PlannerAutoAssistPanel>) {
  return render(
    <I18nProvider>
      <PlannerAutoAssistPanel {...props} />
    </I18nProvider>,
  )
}

describe('PlannerAutoAssistPanel', () => {
  beforeEach(() => {
    localStorage.setItem('unipilot_locale', 'he')
  })

  it('renders auto-assist controls in Hebrew', () => {
    render(
      <I18nProvider>
        <PlannerAutoAssistPanel
          semesterCode="2025-2"
          semesterSelected
          pickingCourses={false}
          onAutoPickCourses={vi.fn()}
        />
      </I18nProvider>,
    )

    expect(screen.getByTestId('planner-auto-assist-panel')).toBeInTheDocument()
    expect(screen.getByTestId('planner-auto-pick-button')).toHaveTextContent(/בחירת קורסים אוטומטית/)
  })

  it('calls onAutoPickCourses with parsed max credits', async () => {
    const user = userEvent.setup()
    const onAutoPickCourses = vi.fn()

    render(
      <I18nProvider>
        <PlannerAutoAssistPanel
          semesterCode="2025-2"
          semesterSelected
          defaultMaxCredits={18}
          pickingCourses={false}
          onAutoPickCourses={onAutoPickCourses}
        />
      </I18nProvider>,
    )

    const creditsInput = screen.getByLabelText(/מקסימום נק״ז|Max credits/i)
    await user.clear(creditsInput)
    await user.type(creditsInput, '9')
    await user.click(screen.getByTestId('planner-auto-pick-button'))

    expect(onAutoPickCourses).toHaveBeenCalledWith(9)
  })

  it('shows localized status message without backend English summary', () => {
    render(
      <I18nProvider>
        <PlannerAutoAssistPanel
          semesterCode="2025-2"
          semesterSelected
          pickingCourses={false}
          statusMessage="נוספו 2 קורסים מומלצים (4 מתוך 18 נק״ז). לא נמצאו עוד קורסים מתאימים לסמסטר זה — אפשר להוסיף ידנית."
          onAutoPickCourses={vi.fn()}
        />
      </I18nProvider>,
    )

    const status = screen.getByTestId('planner-auto-pick-status')
    expect(status).toHaveTextContent(/נוספו 2 קורסים מומלצים/)
    expect(status).not.toHaveTextContent(/Partial plan generated/i)
  })

  it('syncs max credits when profile default loads after mount', () => {
    const { rerender } = renderPanel({
      semesterCode: '2025-2',
      semesterSelected: true,
      pickingCourses: false,
      onAutoPickCourses: vi.fn(),
    })

    const creditsInput = screen.getByLabelText(/מקסימום נק״ז|Max credits/i)
    expect(creditsInput).toHaveValue(18)

    rerender(
      <I18nProvider>
        <PlannerAutoAssistPanel
          semesterCode="2025-2"
          semesterSelected
          defaultMaxCredits={22}
          pickingCourses={false}
          onAutoPickCourses={vi.fn()}
        />
      </I18nProvider>,
    )

    expect(creditsInput).toHaveValue(22)
  })

  it('blocks auto-pick when semester is invalid', async () => {
    const user = userEvent.setup()
    const onAutoPickCourses = vi.fn()

    render(
      <I18nProvider>
        <PlannerAutoAssistPanel
          semesterCode="2025-9"
          semesterSelected
          pickingCourses={false}
          onAutoPickCourses={onAutoPickCourses}
        />
      </I18nProvider>,
    )

    await user.click(screen.getByTestId('planner-auto-pick-button'))
    expect(onAutoPickCourses).not.toHaveBeenCalled()
    expect(screen.getByText(/קוד סמסטר חייב להיות|semester code must/i)).toBeInTheDocument()
  })
})
