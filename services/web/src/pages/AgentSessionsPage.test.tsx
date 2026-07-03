import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { AgentSessionsPage } from './AgentSessionsPage'
import { I18nProvider } from '../i18n'

vi.mock('../api/endpoints', () => ({
  agentSessionsApi: {
    create: vi.fn(),
    get: vi.fn(),
    list: vi.fn().mockResolvedValue({ sessions: [] }),
    replay: vi.fn().mockResolvedValue({ events: [] }),
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
          <AgentSessionsPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('AgentSessionsPage', () => {
  it('renders agent session shell and goal input', () => {
    renderPage()
    expect(screen.getByTestId('agent-sessions-page')).toBeInTheDocument()
    expect(screen.getByTestId('agent-sessions-goal-input')).toBeInTheDocument()
    expect(screen.getByTestId('agent-sessions-start')).toBeInTheDocument()
  })
})
