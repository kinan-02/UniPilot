import { describe, expect, it } from 'vitest'
import { QueryClient } from '@tanstack/react-query'
import { resetAuthScopedQueryCache } from './authQueryCache'

describe('resetAuthScopedQueryCache', () => {
  it('removes all cached queries', () => {
    const queryClient = new QueryClient()
    queryClient.setQueryData(['plans'], { plans: [], pagination: { total: 0 } })
    queryClient.setQueryData(['profile', 'user-1'], { profile: { id: 'p1' } })
    queryClient.setQueryData(['progress'], { graduationProgress: null })

    resetAuthScopedQueryCache(queryClient)

    expect(queryClient.getQueryData(['plans'])).toBeUndefined()
    expect(queryClient.getQueryData(['profile', 'user-1'])).toBeUndefined()
    expect(queryClient.getQueryData(['progress'])).toBeUndefined()
  })
})
