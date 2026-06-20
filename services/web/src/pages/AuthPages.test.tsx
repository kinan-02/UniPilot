import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { I18nProvider } from '../i18n'
import { AuthProvider } from '../auth/AuthContext'
import { LoginPage } from '../pages/AuthPages'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  authApi: {
    me: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
  },
}))

function renderLogin() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <MemoryRouter>
            <LoginPage />
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

    renderLogin()
    await user.type(screen.getByLabelText(/אימייל/i), 'demo@example.com')
    await user.type(screen.getByLabelText(/סיסמה/i), 'StrongPass123!')
    await user.click(screen.getByRole('button', { name: /התחברות/i }))

    await waitFor(() => {
      expect(endpoints.authApi.login).toHaveBeenCalledWith('demo@example.com', 'StrongPass123!')
    })
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
