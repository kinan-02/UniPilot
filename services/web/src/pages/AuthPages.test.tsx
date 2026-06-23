import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from '../i18n'
import { AuthProvider } from '../auth/AuthContext'
import { LoginPage } from '../pages/AuthPages'
import * as endpoints from '../api/endpoints'
import { ApiError } from '../lib/api'

vi.mock('../api/endpoints', () => ({
  authApi: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
  },
  profileApi: { get: vi.fn() },
}))

function renderLogin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <MemoryRouter initialEntries={['/login']}>
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route path="/onboarding" element={<p>Onboarding page</p>} />
              <Route path="/" element={<p>Dashboard page</p>} />
            </Routes>
          </MemoryRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>,
  )
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.authApi.me).mockRejectedValue(new Error('no token'))
  })

  it('renders sign in form in Hebrew by default', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: /התחברות/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/אימייל/i)).toBeInTheDocument()
  })

  it('submits credentials', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.authApi.login).mockResolvedValue({
      accessToken: 'token-123',
      user: { id: '1', email: 'demo@example.com', status: 'active' },
    })
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )

    renderLogin()
    await user.type(screen.getByLabelText(/אימייל/i), 'demo@example.com')
    await user.type(screen.getByLabelText(/סיסמה/i), 'StrongPass123!')
    await user.click(screen.getByRole('button', { name: /התחברות/i }))

    await waitFor(() => {
      expect(endpoints.authApi.login).toHaveBeenCalledWith('demo@example.com', 'StrongPass123!')
    })
    expect(await screen.findByText('Onboarding page')).toBeInTheDocument()
  })

  it('navigates to the dashboard when the user already has a profile', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.authApi.login).mockResolvedValue({
      accessToken: 'token-123',
      user: { id: '1', email: 'demo@example.com', status: 'active' },
    })
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

    renderLogin()
    await user.type(screen.getByLabelText(/אימייל/i), 'demo@example.com')
    await user.type(screen.getByLabelText(/סיסמה/i), 'StrongPass123!')
    await user.click(screen.getByRole('button', { name: /התחברות/i }))

    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
  })

  it('shows validation error for weak password', async () => {
    const user = userEvent.setup()
    renderLogin()
    await user.type(screen.getByLabelText(/אימייל/i), 'demo@example.com')
    await user.type(screen.getByLabelText(/סיסמה/i), 'weak')
    await user.click(screen.getByRole('button', { name: /התחברות/i }))
    expect(await screen.findByText(/8 תווים/i)).toBeInTheDocument()
  })
})
