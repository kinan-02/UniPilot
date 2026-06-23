import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from '../i18n'
import { AuthProvider } from '../auth/AuthContext'
import { AuthQuerySync } from '../auth/AuthQuerySync'
import { OnboardingPage } from './OnboardingPage'
import * as endpoints from '../api/endpoints'
import { ApiError } from '../lib/api'

vi.mock('../api/endpoints', () => ({
  authApi: { me: vi.fn() },
  profileApi: { get: vi.fn(), create: vi.fn() },
  catalogApi: {
    academicFaculties: vi.fn(),
    pathOptions: vi.fn(),
  },
}))

const faculty = {
  id: 'f1',
  facultyId: 'faculty-dds',
  nameHe: 'הנדסת נתונים',
  institutionId: 'technion',
}

const primaryOption = {
  id: 'opt-dne',
  optionKey: 'technion:dds:track-data-information-engineering',
  facultyId: 'faculty-dds',
  wikiSlug: 'track-data-information-engineering',
  kind: 'bsc_track',
  nameHe: 'הנדסת נתונים ומידע',
  selectableAsPrimary: true,
  linkedDegreeProgramId: 'degree-dne',
}

function renderOnboarding(initialPath = '/onboarding') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <AuthQuerySync />
          <MemoryRouter initialEntries={[initialPath]}>
            <Routes>
              <Route path="/onboarding" element={<OnboardingPage />} />
              <Route path="/" element={<p>Dashboard page</p>} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('OnboardingPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.authApi.me).mockResolvedValue({
      user: { id: 'u1', email: 'demo@example.com', status: 'active' },
    })
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    vi.mocked(endpoints.catalogApi.academicFaculties).mockResolvedValue({
      items: [faculty],
      total: 1,
    })
    vi.mocked(endpoints.catalogApi.pathOptions).mockResolvedValue({
      items: [primaryOption],
      total: 1,
    })
  })

  it('shows the first onboarding step when profile is missing', async () => {
    renderOnboarding()
    await waitFor(() => expect(endpoints.profileApi.get).toHaveBeenCalled())
    expect(await screen.findByTestId('program-type-BSc')).toBeInTheDocument()
  })

  it('redirects away when profile already exists', async () => {
    vi.mocked(endpoints.profileApi.get).mockResolvedValue({
      profile: {
        id: 'p1',
        userId: 'u1',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'degree-dne',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })
    renderOnboarding()
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })

  it('creates a profile and navigates to the dashboard', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.profileApi.create).mockResolvedValue({
      profile: {
        id: 'p1',
        userId: 'u1',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'degree-dne',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })

    renderOnboarding()
    await waitFor(() => expect(endpoints.profileApi.get).toHaveBeenCalled())
    await screen.findByTestId('program-type-BSc')

    await user.click(screen.getByTestId('onboarding-continue'))
    await screen.findByRole('heading', { name: /באיזו פקולטה/i })
    await user.click(screen.getByTestId('onboarding-continue'))

    const primaryCard = await screen.findByText('הנדסת נתונים ומידע')
    await user.click(primaryCard)
    await user.click(screen.getByTestId('onboarding-continue'))

    await screen.findByRole('heading', { name: /באיזה סמסטר אתה עכשיו/i })
    await user.click(screen.getByTestId('onboarding-finish'))

    await waitFor(() => {
      expect(endpoints.profileApi.create).toHaveBeenCalledWith(
        expect.objectContaining({
          institutionId: 'technion',
          facultyId: 'faculty-dds',
          programType: 'BSc',
          degreeId: 'degree-dne',
        }),
      )
    })
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })

  it('treats a duplicate profile as success and navigates to the dashboard', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.profileApi.create).mockRejectedValue(
      new ApiError('Student profile already exists for this user', 409),
    )

    renderOnboarding()
    await waitFor(() => expect(endpoints.profileApi.get).toHaveBeenCalled())
    await screen.findByTestId('program-type-BSc')

    await user.click(screen.getByTestId('onboarding-continue'))
    await screen.findByRole('heading', { name: /באיזו פקולטה/i })
    await user.click(screen.getByTestId('onboarding-continue'))

    const primaryCard = await screen.findByText('הנדסת נתונים ומידע')
    await user.click(primaryCard)
    await user.click(screen.getByTestId('onboarding-continue'))

    await screen.findByRole('heading', { name: /באיזה סמסטר אתה עכשיו/i })
    await user.click(screen.getByTestId('onboarding-finish'))

    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })
})
