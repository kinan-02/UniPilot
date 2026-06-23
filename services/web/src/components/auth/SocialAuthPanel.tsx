import { useEffect, useState } from 'react'
import { authApi, googleSignInUrl } from '../../api/endpoints'
import { Button } from '../ui/Button'
import { useTranslation } from '../../i18n'

type SocialAuthPanelProps = {
  rememberMe: boolean
}

export function SocialAuthPanel({ rememberMe }: SocialAuthPanelProps) {
  const { t } = useTranslation()
  const [googleEnabled, setGoogleEnabled] = useState(false)

  useEffect(() => {
    let cancelled = false
    authApi
      .providers()
      .then((providers) => {
        if (!cancelled) setGoogleEnabled(providers.google)
      })
      .catch(() => {
        if (!cancelled) setGoogleEnabled(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!googleEnabled) {
    return null
  }

  return (
    <div className="space-y-3">
      <div className="relative py-1">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t border-[var(--color-border)]" />
        </div>
        <div className="relative flex justify-center text-xs uppercase tracking-wide">
          <span className="bg-[var(--color-surface)] px-2 text-[var(--color-text-muted)]">
            {t('auth.orContinueWith')}
          </span>
        </div>
      </div>
      <Button
        type="button"
        variant="secondary"
        className="w-full"
        onClick={() => {
          window.location.assign(googleSignInUrl(rememberMe))
        }}
      >
        {t('auth.continueWithGoogle')}
      </Button>
    </div>
  )
}
