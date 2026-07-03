import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from '../i18n'
import { AuthProvider } from '../auth/AuthContext'
import { AgentPage } from './AgentPage'

vi.mock('../hooks/useAgentChat', () => ({
  useAgentConversations: () => ({
    conversations: [],
    createConversation: vi.fn().mockResolvedValue({ conversation: { id: 'conv-1' } }),
    isCreating: false,
  }),
  useAgentChat: () => ({
    messages: [],
    liveTurn: null,
    isStreaming: false,
    suggestedPrompts: [],
    pendingActions: [],
    sendMessage: vi.fn(),
    stopStreaming: vi.fn(),
    confirmAction: { mutate: vi.fn(), isPending: false },
    rejectAction: { mutate: vi.fn(), isPending: false },
    clearLiveTurn: vi.fn(),
    refetch: vi.fn(),
  }),
}))

vi.mock('../api/endpoints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/endpoints')>()
  return {
    ...actual,
    profileApi: {
      get: vi.fn().mockRejectedValue(new Error('no profile')),
    },
  }
})

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={['/agent']}>
            <AgentPage />
          </MemoryRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('AgentPage', () => {
  it('renders the agent shell and empty state', () => {
    renderPage()
    expect(screen.getByTestId('agent-page')).toBeInTheDocument()
    expect(screen.getByTestId('agent-empty-state')).toBeInTheDocument()
    expect(screen.getByTestId('agent-composer')).toBeInTheDocument()
  })
})
