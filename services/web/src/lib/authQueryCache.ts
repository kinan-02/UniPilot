import type { QueryClient } from '@tanstack/react-query'

/** Drop all cached server state when the signed-in user changes or signs out. */
export function resetAuthScopedQueryCache(queryClient: QueryClient) {
  queryClient.clear()
}
