import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { DashboardPage } from './DashboardPage'
import * as endpoints from '../api/endpoints'
import { ApiError } from '../lib/api'

vi.mock('../api/endpoints', () => ({
  profileApi: { get: vi.fn() },
  progressApi: { get: vi.fn() },
  plansApi: { list: vi.fn() },
  risksApi: { list: vi.fn() },
}))

function renderDashboard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.plansApi.list).mockResolvedValue({
      semesterPlans: [],
      pagination: { total: 0 },
    })
    vi.mocked(endpoints.risksApi.list).mockResolvedValue({
      academicRiskAnalyses: [],
      pagination: { total: 0 },
    })
  })

  it('shows onboarding prompt when profile is missing', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(new ApiError('Not found', 404))
    renderDashboard()
    expect(await screen.findByText(/complete your profile/i)).toBeInTheDocument()
  })

  it('renders dashboard stats when profile exists', async () => {
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
        completionPercentage: 42,
        completedCredits: 60,
        totalRequiredCredits: 140,
        creditsRemaining: 80,
        statusSummary: 'in_progress',
      },
    })

    renderDashboard()
    expect(await screen.findByRole('heading', { name: /hello, bsc student/i })).toBeInTheDocument()
    expect(await screen.findByText('42.0%')).toBeInTheDocument()
  })
})
