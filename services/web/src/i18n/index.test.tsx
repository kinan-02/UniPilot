import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { I18nProvider, useTranslation } from './index'

function Probe() {
  const { t } = useTranslation()
  return (
    <span data-testid="probe">
      {t('transcript.upload.selectedCount', { count: 12 })}
    </span>
  )
}

describe('I18nProvider', () => {
  it('interpolates translation params', () => {
    localStorage.setItem('unipilot_locale', 'he')
    render(
      <I18nProvider>
        <Probe />
      </I18nProvider>,
    )
    expect(screen.getByTestId('probe')).toHaveTextContent('12 נבחרו לייבוא')
  })
})
