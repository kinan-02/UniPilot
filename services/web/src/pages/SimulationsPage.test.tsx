import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { SimulationsPage } from './SimulationsPage'
import { I18nProvider } from '../i18n'

vi.mock('../api/endpoints', () => ({
  simulationsApi: {
    list: vi.fn().mockResolvedValue({ simulationScenarios: [] }),
    get: vi.fn(),
    createFromText: vi.fn(),
    run: vi.fn(),
    listResults: vi.fn().mockResolvedValue({ simulationResults: [] }),
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
          <SimulationsPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('SimulationsPage', () => {
  it('renders simulations shell and builder controls', () => {
    renderPage()
    expect(screen.getByTestId('simulations-page')).toBeInTheDocument()
    expect(screen.getByTestId('simulation-text')).toBeInTheDocument()
    expect(screen.getByTestId('simulation-build')).toBeInTheDocument()
    expect(screen.getByTestId('simulation-prefer-instant')).toBeInTheDocument()
    expect(screen.getByTestId('simulation-history')).toBeInTheDocument()
    expect(screen.getByTestId('simulation-new')).toBeInTheDocument()
  })
})
