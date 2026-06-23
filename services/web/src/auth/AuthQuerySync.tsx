import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { resetStudentProfileCache } from '../lib/studentProfileQuery'

/** Drop cached profile data whenever the signed-in user changes. */
export function AuthQuerySync() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const previousUserIdRef = useRef<string | null>(null)

  useEffect(() => {
    const nextUserId = user?.id ?? null
    if (previousUserIdRef.current !== nextUserId) {
      resetStudentProfileCache(queryClient)
      previousUserIdRef.current = nextUserId
    }
  }, [queryClient, user?.id])

  return null
}
