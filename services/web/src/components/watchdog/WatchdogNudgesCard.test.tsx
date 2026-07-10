import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { WatchdogNudgesCard } from './WatchdogNudgesCard'
import * as endpoints from '../../api/endpoints'
import { I18nProvider } from '../../i18n'

vi.mock('../../api/endpoints', () => ({
  recommendationsApi: {
    list: vi.fn(),
    dismiss: vi.fn(),
  },
}))

vi.mock('../../lib/studentProfileQuery', () => ({
  hasStudentProfile: () => true,
  useStudentProfileQuery: () => ({
    data: { profile: { degreeId: 'd1' } },
    isLoading: false,
  }),
}))

function renderCard() {
  localStorage.setItem('unipilot_locale', 'en')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <WatchdogNudgesCard />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>,
  )
}

describe('WatchdogNudgesCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state when there are no active recommendations', async () => {
    vi.mocked(endpoints.recommendationsApi.list).mockResolvedValue({
      recommendations: [],
      pagination: { total: 0, page: 1, limit: 20 },
    })
    renderCard()
    expect(await screen.findByTestId('watchdog-nudges-empty')).toBeInTheDocument()
    expect(screen.getByText(/no proactive alerts right now/i)).toBeInTheDocument()
    expect(screen.queryByTestId('watchdog-nudges-card')).not.toBeInTheDocument()
  })

  it('renders recommendations and dismisses one', async () => {
    vi.mocked(endpoints.recommendationsApi.list).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          type: 'watchdog_nudge',
          nudgeType: 'pace',
          severity: 'medium',
          title: 'Behind on mandatory courses',
          body: 'Two matrix courses are still open.',
          status: 'active',
        },
      ],
      pagination: { total: 1, page: 1, limit: 20 },
    })
    vi.mocked(endpoints.recommendationsApi.dismiss).mockResolvedValue({
      recommendation: {
        id: 'rec-1',
        type: 'watchdog_nudge',
        title: 'Behind on mandatory courses',
        body: 'Two matrix courses are still open.',
        status: 'dismissed',
      },
    })

    const user = userEvent.setup()
    renderCard()

    expect(await screen.findByTestId('watchdog-nudges-card')).toBeInTheDocument()
    expect(screen.getByText('Behind on mandatory courses')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /review progress/i })).toHaveAttribute(
      'href',
      '/progress#progress-attention',
    )

    await user.click(screen.getAllByRole('button', { name: /dismiss/i })[0]!)
    await waitFor(() => {
      expect(endpoints.recommendationsApi.dismiss).toHaveBeenCalledWith('rec-1')
    })
  })
})
