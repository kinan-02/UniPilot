import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AdvisorPage } from './AdvisorPage'
import { I18nProvider } from '../i18n'

vi.mock('../api/endpoints', () => ({
  advisorApi: {
    ask: vi.fn(),
  },
}))

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <AdvisorPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('AdvisorPage', () => {
  it('renders advisor shell and suggested prompts', () => {
    renderPage()
    expect(screen.getByTestId('advisor-page')).toBeInTheDocument()
    expect(screen.getByTestId('advisor-input')).toBeInTheDocument()
    expect(screen.getByTestId('advisor-submit')).toBeInTheDocument()
  })
})
