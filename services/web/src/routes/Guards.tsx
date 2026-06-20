import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { profileApi } from '../api/endpoints'
import { useAuth, isAuthError } from '../auth/AuthContext'
import { Spinner } from '../components/ui/Card'

export function ProtectedRoute() {
  const { token, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (!token) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

export function PublicOnlyRoute() {
  const { token, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (token) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}

export function ProfileGuard() {
  const location = useLocation()
  const profileQuery = useQuery({
    queryKey: ['profile'],
    queryFn: async () => {
      try {
        return await profileApi.get()
      } catch (err) {
        if (isAuthError(err) && err.status === 404) return null
        throw err
      }
    },
    retry: false,
  })

  if (profileQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (profileQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="text-sm text-[var(--color-danger)]">
          {isAuthError(profileQuery.error)
            ? profileQuery.error.message
            : 'Could not load your profile.'}
        </p>
      </div>
    )
  }

  if (!profileQuery.data?.profile) {
    return <Navigate to="/onboarding" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
