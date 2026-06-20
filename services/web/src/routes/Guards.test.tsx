import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from '../i18n'
import { ProfileGuard, ProtectedRoute } from './Guards'
import * as endpoints from '../api/endpoints'
import { AuthProvider } from '../auth/AuthContext'
import { ApiError } from '../lib/api'

vi.mock('../api/endpoints', () => ({
  authApi: { me: vi.fn() },
  profileApi: { get: vi.fn() },
}))

function renderWithRoutes(initialPath: string, element: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={[initialPath]}>
          <Routes>
            <Route element={element}>
              <Route path="/app" element={<p>App content</p>} />
            </Route>
            <Route path="/login" element={<p>Login page</p>} />
            <Route path="/onboarding" element={<p>Onboarding page</p>} />
          </Routes>
        </MemoryRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('redirects unauthenticated users to login', async () => {
    vi.mocked(endpoints.authApi.me).mockRejectedValue(new Error('no token'))
    renderWithRoutes('/app', <ProtectedRoute />)
    expect(await screen.findByText('Login page')).toBeInTheDocument()
  })
})

describe('ProfileGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.setItem('unipilot_access_token', 'test-token')
    vi.mocked(endpoints.authApi.me).mockResolvedValue({
      user: { id: '1', email: 'demo@example.com', status: 'active' },
    })
  })

  it('redirects to onboarding when profile is missing', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(new ApiError('Not found', 404))
    renderWithRoutes('/app', <ProfileGuard />)
    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
  })

  it('renders child routes when profile exists', async () => {
    vi.mocked(endpoints.profileApi.get).mockResolvedValue({
      profile: {
        id: 'p1',
        userId: '1',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'deg1',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })
    renderWithRoutes('/app', <ProfileGuard />)
    expect(await screen.findByText('App content')).toBeInTheDocument()
  })
})
