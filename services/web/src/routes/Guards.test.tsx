import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from '../i18n'
import {
  AuthenticatedHomeRedirect,
  ProfileGuard,
  ProtectedRoute,
  PublicOnlyRoute,
} from './Guards'
import * as endpoints from '../api/endpoints'
import { AuthProvider } from '../auth/AuthContext'
import { AuthQuerySync } from '../auth/AuthQuerySync'
import { ApiError } from '../lib/api'
import { STUDENT_PROFILE_QUERY_KEY } from '../lib/studentProfileQuery'

vi.mock('../api/endpoints', () => ({
  authApi: { me: vi.fn() },
  profileApi: { get: vi.fn() },
}))

const authenticatedUser = { id: '1', email: 'demo@example.com', status: 'active' as const }

function renderAppRoutes(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <AuthQuerySync />
          <MemoryRouter initialEntries={[initialPath]}>
            <Routes>
              <Route path="/app" element={<ProtectedRoute />}>
                <Route
                  index
                  element={
                    <ProfileGuard>
                      <p>App content</p>
                    </ProfileGuard>
                  }
                />
              </Route>
              <Route path="/register" element={<PublicOnlyRoute />}>
                <Route index element={<p>Register page</p>} />
              </Route>
              <Route path="/onboarding" element={<p>Onboarding page</p>} />
              <Route path="/login" element={<p>Login page</p>} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

function renderProfileGuard(initialPath: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <AuthQuerySync />
          <MemoryRouter initialEntries={[initialPath]}>
            <Routes>
              <Route path="/app" element={<ProtectedRoute />}>
                <Route element={<ProfileGuard />}>
                  <Route index element={<p>App content</p>} />
                </Route>
              </Route>
              <Route path="/onboarding" element={<p>Onboarding page</p>} />
              <Route path="/login" element={<p>Login page</p>} />
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
    renderAppRoutes('/app')
    await waitFor(() => {
      expect(screen.getByText('Login page')).toBeInTheDocument()
    })
  })
})

describe('PublicOnlyRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.authApi.me).mockResolvedValue({ user: authenticatedUser })
  })

  it('redirects authenticated users without a profile to onboarding', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    renderAppRoutes('/register')
    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
  })
})

describe('AuthenticatedHomeRedirect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.authApi.me).mockResolvedValue({ user: authenticatedUser })
  })

  it('redirects to onboarding when profile is missing', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider>
          <AuthProvider>
            <AuthQuerySync />
            <MemoryRouter initialEntries={['/register']}>
              <Routes>
                <Route path="/" element={<p>Dashboard page</p>} />
                <Route path="/onboarding" element={<p>Onboarding page</p>} />
                <Route path="/register" element={<AuthenticatedHomeRedirect />} />
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </I18nProvider>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
  })

  it('redirects to the dashboard when profile exists', async () => {
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
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider>
          <AuthProvider>
            <AuthQuerySync />
            <MemoryRouter initialEntries={['/register']}>
              <Routes>
                <Route path="/" element={<p>Dashboard page</p>} />
                <Route path="/onboarding" element={<p>Onboarding page</p>} />
                <Route path="/register" element={<AuthenticatedHomeRedirect />} />
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </I18nProvider>
      </QueryClientProvider>,
    )
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })

  it('does not redirect to dashboard when stale profile cache belongs to another user', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData([...STUDENT_PROFILE_QUERY_KEY, 'old-user'], {
      profile: {
        id: 'p-old',
        userId: 'old-user',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'deg1',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })

    vi.mocked(endpoints.authApi.me).mockResolvedValue({ user: authenticatedUser })
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <AuthProvider>
            <AuthQuerySync />
            <MemoryRouter initialEntries={['/register']}>
              <Routes>
                <Route path="/" element={<p>Dashboard page</p>} />
                <Route path="/onboarding" element={<p>Onboarding page</p>} />
                <Route path="/register" element={<AuthenticatedHomeRedirect />} />
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </I18nProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
    expect(screen.queryByText('Dashboard page')).not.toBeInTheDocument()
  })
})

describe('ProfileGuard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.authApi.me).mockResolvedValue({ user: authenticatedUser })
  })

  it('redirects to onboarding when profile is missing', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    renderProfileGuard('/app')
    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
  })

  it('does not show the raw API error when profile is missing', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    renderProfileGuard('/app')
    await screen.findByText('Onboarding page')
    expect(screen.queryByText('Student profile not found')).not.toBeInTheDocument()
  })

  it('does not render app content when stale profile cache belongs to another user', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData([...STUDENT_PROFILE_QUERY_KEY, 'old-user'], {
      profile: {
        id: 'p-old',
        userId: 'old-user',
        institutionId: 'technion',
        programType: 'BSc',
        degreeId: 'deg1',
        catalogYear: 2025,
        currentSemesterCode: '2025-1',
      },
    })

    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )

    render(
      <QueryClientProvider client={queryClient}>
        <I18nProvider>
          <AuthProvider>
            <AuthQuerySync />
            <MemoryRouter initialEntries={['/app']}>
              <Routes>
                <Route path="/app" element={<ProtectedRoute />}>
                  <Route element={<ProfileGuard />}>
                    <Route index element={<p>App content</p>} />
                  </Route>
                </Route>
                <Route path="/onboarding" element={<p>Onboarding page</p>} />
                <Route path="/login" element={<p>Login page</p>} />
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </I18nProvider>
      </QueryClientProvider>,
    )

    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
    expect(screen.queryByText('App content')).not.toBeInTheDocument()
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
    renderProfileGuard('/app')
    expect(await screen.findByText('App content')).toBeInTheDocument()
  })
})
