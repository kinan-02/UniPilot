import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { resetAuthScopedQueryCache } from '../lib/authQueryCache'

/** Drop cached user data whenever the signed-in user changes or signs out. */
export function AuthQuerySync() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const previousUserIdRef = useRef<string | null>(null)

  useEffect(() => {
    const nextUserId = user?.id ?? null
    if (previousUserIdRef.current !== nextUserId) {
      resetAuthScopedQueryCache(queryClient)
      previousUserIdRef.current = nextUserId
    }
  }, [queryClient, user?.id])

  return null
}
