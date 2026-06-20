import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest, getStoredToken, setStoredToken } from './api'

describe('api helpers', () => {
  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('stores and reads JWT token', () => {
    expect(getStoredToken()).toBeNull()
    setStoredToken('abc')
    expect(getStoredToken()).toBe('abc')
    setStoredToken(null)
    expect(getStoredToken()).toBeNull()
  })

  it('throws ApiError on failed envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ success: false, data: null, error: 'Unauthorized' }),
      }),
    )

    await expect(apiRequest('/auth/me')).rejects.toMatchObject({
      message: 'Unauthorized',
      status: 401,
    })
  })

  it('returns data from successful envelope', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ success: true, data: { ok: true }, error: null }),
      }),
    )

    await expect(apiRequest<{ ok: boolean }>('/health')).resolves.toEqual({ ok: true })
  })

  it('ApiError exposes status code', () => {
    const err = new ApiError('Bad request', 400)
    expect(err.status).toBe(400)
    expect(err.message).toBe('Bad request')
  })
})
