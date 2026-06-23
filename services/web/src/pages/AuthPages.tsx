import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { isAuthError, useAuth } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Card } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { validateEmail, validatePassword } from '../lib/validation'
import {
  fetchStudentProfileOrNull,
  hasStudentProfile,
  resetStudentProfileCache,
} from '../lib/studentProfileQuery'
import { SocialAuthPanel } from '../components/auth/SocialAuthPanel'

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  google_denied: 'auth.googleDenied',
  google_account_exists: 'auth.googleAccountExists',
  google_auth_failed: 'auth.googleSignInFailed',
  google_invalid_state: 'auth.googleSignInFailed',
  google_email_unverified: 'auth.googleEmailUnverified',
  google_not_configured: 'auth.googleNotConfigured',
}

export function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle: string
  children: React.ReactNode
}) {
  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md animate-fade-in">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--color-primary)] text-lg font-bold text-white shadow-[var(--shadow-card)]">
            UP
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          <p className="mt-2 text-sm text-[var(--color-text-muted)]">{subtitle}</p>
        </div>
        <Card>{children}</Card>
      </div>
    </div>
  )
}

export function LoginPage() {
  const { login } = useAuth()
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(true)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const oauthError = searchParams.get('error')
    if (!oauthError) return
    const messageKey = AUTH_ERROR_MESSAGES[oauthError] ?? 'auth.googleSignInFailed'
    setError(t(messageKey))
  }, [searchParams, t])

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')

    const emailResult = validateEmail(email)
    if (!emailResult.ok) {
      setError(t(emailResult.message))
      return
    }
    const passwordResult = validatePassword(password)
    if (!passwordResult.ok) {
      setError(t(passwordResult.message))
      return
    }

    setLoading(true)
    try {
      await login(email.trim(), password, rememberMe)
      resetStudentProfileCache(queryClient)
      const profileData = await fetchStudentProfileOrNull()
      navigate(hasStudentProfile(profileData) ? '/' : '/onboarding', { replace: true })
    } catch (err) {
      setError(isAuthError(err) ? err.message : t('auth.signInFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title={t('auth.welcomeBack')} subtitle={t('auth.signInSubtitle')}>
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Input
          id="email"
          label={t('auth.email')}
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          id="password"
          label={t('auth.password')}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
          <input
            type="checkbox"
            checked={rememberMe}
            onChange={(event) => setRememberMe(event.target.checked)}
            className="h-4 w-4 rounded border-[var(--color-border)]"
          />
          {t('auth.rememberMe')}
        </label>
        {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
        <Button type="submit" className="w-full" loading={loading}>
          {t('auth.signIn')}
        </Button>
        <SocialAuthPanel rememberMe={rememberMe} />
        <p className="text-center text-sm text-[var(--color-text-muted)]">
          {t('auth.newHere')}{' '}
          <Link className="font-medium text-[var(--color-primary)] hover:underline" to="/register">
            {t('auth.register')}
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}

export function RegisterPage() {
  const { register } = useAuth()
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')

    const emailResult = validateEmail(email)
    if (!emailResult.ok) {
      setError(t(emailResult.message))
      return
    }
    const passwordResult = validatePassword(password)
    if (!passwordResult.ok) {
      setError(t(passwordResult.message))
      return
    }

    setLoading(true)
    try {
      await register(email.trim(), password)
      resetStudentProfileCache(queryClient)
      navigate('/onboarding', { replace: true })
    } catch (err) {
      setError(isAuthError(err) ? err.message : t('auth.registerFailed'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthShell title={t('auth.createAccount')} subtitle={t('auth.registerSubtitle')}>
      <form className="space-y-4" onSubmit={handleSubmit}>
        <Input
          id="email"
          label={t('auth.email')}
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          id="password"
          label={t('auth.password')}
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
        <p className="text-xs text-[var(--color-text-muted)]">{t('auth.passwordHint')}</p>
        {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
        <Button type="submit" className="w-full" loading={loading}>
          {t('auth.register')}
        </Button>
        <SocialAuthPanel rememberMe />
        <p className="text-center text-sm text-[var(--color-text-muted)]">
          {t('auth.haveAccount')}{' '}
          <Link className="font-medium text-[var(--color-primary)] hover:underline" to="/login">
            {t('auth.signIn')}
          </Link>
        </p>
      </form>
    </AuthShell>
  )
}
