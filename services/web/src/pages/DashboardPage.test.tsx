import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardPage } from './DashboardPage'
import * as endpoints from '../api/endpoints'
import { ApiError } from '../lib/api'
import { AuthProvider } from '../auth/AuthContext'
import { AuthQuerySync } from '../auth/AuthQuerySync'
import { I18nProvider } from '../i18n'

vi.mock('../api/endpoints', () => ({
  authApi: { me: vi.fn() },
  profileApi: { get: vi.fn() },
  progressApi: { get: vi.fn() },
  plansApi: { list: vi.fn() },
  risksApi: { list: vi.fn() },
  recommendationsApi: { list: vi.fn() },
}))

function renderDashboard() {
  localStorage.setItem('unipilot_locale', 'en')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthQuerySync />
          <MemoryRouter>
            <DashboardPage />
          </MemoryRouter>
        </AuthProvider>
      </QueryClientProvider>
    </I18nProvider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.authApi.me).mockResolvedValue({
      user: { id: 'u1', email: 'demo@example.com', status: 'active' },
    })
    vi.mocked(endpoints.plansApi.list).mockResolvedValue({
      semesterPlans: [],
      pagination: { total: 0 },
    })
    vi.mocked(endpoints.risksApi.list).mockResolvedValue({
      academicRiskAnalyses: [],
      pagination: { total: 0 },
    })
    vi.mocked(endpoints.recommendationsApi.list).mockResolvedValue({
      recommendations: [],
      pagination: { total: 0, page: 1, limit: 20 },
    })
  })

  it('shows onboarding prompt when profile is missing', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    renderDashboard()
    await waitFor(() => {
      expect(endpoints.profileApi.get).toHaveBeenCalled()
    })
    expect(await screen.findByTestId('dashboard-setup-prompt')).toBeInTheDocument()
    expect(screen.getByText(/complete your profile/i)).toBeInTheDocument()
    expect(screen.queryByText('Student profile not found')).not.toBeInTheDocument()
  })

  it('renders credit-first progress hero and quick actions when profile exists', async () => {
    vi.mocked(endpoints.profileApi.get).mockResolvedValue({
      profile: {
        id: 'p1',
        userId: 'u1',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'd1',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: {
        degreeId: 'd1',
        degreeCode: '006',
        degreeName: 'Industrial Engineering',
        catalogYear: 2025,
        completionPercentage: 42,
        completedCredits: 60,
        totalRequiredCredits: 140,
        creditsRemaining: 80,
        statusSummary: 'in_progress',
      },
    })

    renderDashboard()
    expect(await screen.findByRole('heading', { name: /hello, bsc student/i })).toBeInTheDocument()
    expect(await screen.findByTestId('dashboard-progress-hero')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-credits-hero')).toHaveTextContent('60')
    expect(screen.getByTestId('dashboard-credits-hero')).toHaveTextContent('140')
    expect(screen.getByText('42.0%')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-view-progress-link')).toHaveAttribute('href', '/progress')
    expect(screen.getByTestId('dashboard-quick-actions')).toBeInTheDocument()
    expect(screen.getByTestId('dashboard-action-transcript')).toBeInTheDocument()
    expect(screen.getByText('2025-1')).toBeInTheDocument()
  })

  it('renders proactive watchdog nudges when recommendations exist', async () => {
    vi.mocked(endpoints.profileApi.get).mockResolvedValue({
      profile: {
        id: 'p1',
        userId: 'u1',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'd1',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: {
        degreeId: 'd1',
        completionPercentage: 42,
        completedCredits: 60,
        totalRequiredCredits: 140,
        statusSummary: 'in_progress',
      },
    })
    vi.mocked(endpoints.recommendationsApi.list).mockResolvedValue({
      recommendations: [
        {
          id: 'rec-1',
          type: 'watchdog_nudge',
          nudgeType: 'risk',
          severity: 'high',
          title: 'High-severity academic risk detected',
          body: 'Your latest risk analysis flagged issues.',
          status: 'active',
        },
      ],
      pagination: { total: 1, page: 1, limit: 20 },
    })

    renderDashboard()
    expect(await screen.findByTestId('watchdog-nudges-card')).toBeInTheDocument()
    expect(screen.getByText('High-severity academic risk detected')).toBeInTheDocument()
  })

  it('shows loading skeleton while profile loads', async () => {
    vi.mocked(endpoints.profileApi.get).mockReturnValue(new Promise(() => undefined))
    renderDashboard()
    expect(await screen.findByTestId('dashboard-loading-skeleton')).toBeInTheDocument()
  })
})
