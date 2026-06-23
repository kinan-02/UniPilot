import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../lib/api'
import {
  fetchStudentProfileOrNull,
  studentProfileQueryOptions,
} from './studentProfileQuery'
import * as endpoints from '../api/endpoints'

vi.mock('../api/endpoints', () => ({
  profileApi: { get: vi.fn() },
}))

describe('fetchStudentProfileOrNull', () => {
  it('returns null when the API responds with 404', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    await expect(fetchStudentProfileOrNull()).resolves.toBeNull()
  })

  it('rethrows non-404 errors', async () => {
    vi.mocked(endpoints.profileApi.get).mockRejectedValue(new ApiError('Unauthorized', 401))
    await expect(fetchStudentProfileOrNull()).rejects.toMatchObject({ status: 401 })
  })
})

describe('studentProfileQueryOptions', () => {
  it('scopes the query key to the signed-in user', () => {
    expect(studentProfileQueryOptions('user-1').queryKey).toEqual(['profile', 'user-1'])
    expect(studentProfileQueryOptions(undefined).enabled).toBe(false)
  })
})
