import { Link, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { isAuthError, useAuth } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Card } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { validateEmail, validatePassword } from '../lib/validation'

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
      await login(email.trim(), password)
      navigate('/')
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
        {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
        <Button type="submit" className="w-full" loading={loading}>
          {t('auth.signIn')}
        </Button>
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
      navigate('/onboarding')
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
