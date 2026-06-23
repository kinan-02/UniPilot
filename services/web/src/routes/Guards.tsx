import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { isAuthError, useAuth } from '../auth/AuthContext'
import { Spinner } from '../components/ui/Card'
import {
  hasStudentProfile,
  useStudentProfileQuery,
} from '../lib/studentProfileQuery'

function FullScreenSpinner() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <Spinner />
    </div>
  )
}

function ProfileBootstrapScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <p className="text-sm text-[var(--color-text-muted)]">Loading your account…</p>
    </div>
  )
}

export function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  if (isLoading) {
    return <FullScreenSpinner />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}

/** Sends authenticated users away from login/register to the right post-auth destination. */
export function PublicOnlyRoute() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <FullScreenSpinner />
  }

  if (isAuthenticated) {
    return <AuthenticatedHomeRedirect />
  }

  return <Outlet />
}

export function AuthenticatedHomeRedirect() {
  const { user, isLoading: authLoading } = useAuth()
  const profileQuery = useStudentProfileQuery()

  if (authLoading || !user) {
    return <ProfileBootstrapScreen />
  }

  if (profileQuery.isLoading) {
    return <ProfileBootstrapScreen />
  }

  if (profileQuery.isError) {
    if (isAuthError(profileQuery.error) && profileQuery.error.status === 404) {
      return <Navigate to="/onboarding" replace />
    }
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="text-sm text-[var(--color-danger)]">
          Could not load your profile. Please try again.
        </p>
      </div>
    )
  }

  if (!hasStudentProfile(profileQuery.data)) {
    return <Navigate to="/onboarding" replace />
  }

  return <Navigate to="/" replace />
}

export function ProfileGuard() {
  const location = useLocation()
  const { user, isLoading: authLoading } = useAuth()
  const profileQuery = useStudentProfileQuery()

  if (authLoading || !user) {
    return <FullScreenSpinner />
  }

  if (profileQuery.isLoading) {
    return <FullScreenSpinner />
  }

  if (profileQuery.isError) {
    if (isAuthError(profileQuery.error) && profileQuery.error.status === 404) {
      return <Navigate to="/onboarding" replace state={{ from: location.pathname }} />
    }
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <p className="text-sm text-[var(--color-danger)]">
          Could not load your profile. Please try again.
        </p>
      </div>
    )
  }

  if (!hasStudentProfile(profileQuery.data)) {
    return <Navigate to="/onboarding" replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
