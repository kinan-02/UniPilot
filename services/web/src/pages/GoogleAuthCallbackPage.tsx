import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../auth/AuthContext'
import { useTranslation } from '../i18n'
import {
  fetchStudentProfileOrNull,
  hasStudentProfile,
  resetStudentProfileCache,
} from '../lib/studentProfileQuery'
import { AuthShell } from './AuthPages'

export function GoogleAuthCallbackPage() {
  const { t } = useTranslation()
  const { refreshUser } = useAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false

    async function completeSignIn() {
      try {
        await refreshUser()
        if (cancelled) return
        resetStudentProfileCache(queryClient)
        const profileData = await fetchStudentProfileOrNull()
        if (cancelled) return
        navigate(hasStudentProfile(profileData) ? '/' : '/onboarding', { replace: true })
      } catch {
        if (!cancelled) {
          setError(t('auth.googleSignInFailed'))
        }
      }
    }

    void completeSignIn()

    return () => {
      cancelled = true
    }
  }, [navigate, queryClient, refreshUser, t])

  return (
    <AuthShell title={t('auth.googleSigningIn')} subtitle={t('auth.googleSigningInSubtitle')}>
      {error ? (
        <p className="text-center text-sm text-[var(--color-danger)]">{error}</p>
      ) : (
        <p className="text-center text-sm text-[var(--color-text-muted)]">{t('common.loading')}</p>
      )}
    </AuthShell>
  )
}
