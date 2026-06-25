import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthQuerySync } from './AuthQuerySync'
import { AuthProvider } from './AuthContext'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  authApi: {
    me: vi.fn(),
  },
}))

describe('AuthQuerySync', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('clears non-profile cached queries when the signed-in user changes', async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    queryClient.setQueryData(['plans'], { plans: [{ id: 'old-plan' }], pagination: { total: 1 } })
    queryClient.setQueryData(['profile', 'old-user'], {
      profile: { id: 'p-old', userId: 'old-user' },
    })

    vi.mocked(endpoints.authApi.me).mockResolvedValue({
      user: { id: 'new-user', email: 'new@example.com', status: 'active' },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <AuthQuerySync />
        </AuthProvider>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(queryClient.getQueryData(['plans'])).toBeUndefined()
      expect(queryClient.getQueryData(['profile', 'old-user'])).toBeUndefined()
    })
  })
})
