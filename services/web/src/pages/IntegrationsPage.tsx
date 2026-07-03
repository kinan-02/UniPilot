import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Mail } from 'lucide-react'
import { outlookApi, outlookConnectUrl } from '../api/outlook'
import { isAuthError } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Card, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'

const OUTLOOK_ERROR_CODES = new Set([
  'outlook_not_configured',
  'outlook_denied',
  'outlook_invalid_callback',
  'outlook_invalid_state',
  'outlook_missing_refresh_token',
  'outlook_auth_failed',
])

function resolveOutlookErrorMessage(
  code: string | null,
  t: (key: string) => string,
): string {
  if (!code) return t('integrations.outlook.errors.generic')
  if (OUTLOOK_ERROR_CODES.has(code)) {
    return t(`integrations.outlook.errors.${code}`)
  }
  return t('integrations.outlook.errors.generic')
}

export function IntegrationsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()
  const [banner, setBanner] = useState<{ kind: 'success' | 'error'; message: string } | null>(
    null,
  )

  const statusQuery = useQuery({
    queryKey: ['outlook-status'],
    queryFn: () => outlookApi.status(),
  })

  const disconnectMutation = useMutation({
    mutationFn: () => outlookApi.disconnect(),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['outlook-status'] })
      setBanner({ kind: 'success', message: t('integrations.outlook.disconnectSuccess') })
    },
    onError: (err) => {
      setBanner({
        kind: 'error',
        message: isAuthError(err) ? err.message : t('integrations.outlook.errors.generic'),
      })
    },
  })

  useEffect(() => {
    const outlookParam = searchParams.get('outlook')
    if (!outlookParam) return

    if (outlookParam === 'connected') {
      setBanner({ kind: 'success', message: t('integrations.outlook.connectSuccess') })
      void queryClient.invalidateQueries({ queryKey: ['outlook-status'] })
    } else if (outlookParam === 'error') {
      const code = searchParams.get('code')
      setBanner({
        kind: 'error',
        message: resolveOutlookErrorMessage(code, t),
      })
    }

    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('outlook')
    nextParams.delete('code')
    setSearchParams(nextParams, { replace: true })
  }, [queryClient, searchParams, setSearchParams, t])

  const status = statusQuery.data
  const connected = Boolean(status?.connected)
  const available = Boolean(status?.available)

  const scopesLabel = useMemo(() => {
    const scopes = status?.scopes ?? []
    if (scopes.length === 0) return null
    return scopes.join(', ')
  }, [status?.scopes])

  if (statusQuery.isLoading) {
    return (
      <div className="flex justify-center py-24" data-testid="integrations-loading">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="animate-fade-in" data-testid="integrations-page">
      <PageHeader
        title={t('integrations.title')}
        description={t('integrations.subtitle')}
      />

      {banner ? (
        <p
          className={
            banner.kind === 'success'
              ? 'mb-6 text-sm text-[var(--color-success)]'
              : 'mb-6 text-sm text-[var(--color-danger)]'
          }
          data-testid="integrations-banner"
        >
          {banner.message}
        </p>
      ) : null}

      {statusQuery.isError ? (
        <Card className="max-w-2xl p-6">
          <p className="text-sm text-[var(--color-danger)]">{t('integrations.outlook.loadFailed')}</p>
          <Button className="mt-4" variant="secondary" onClick={() => statusQuery.refetch()}>
            {t('common.retry')}
          </Button>
        </Card>
      ) : (
        <Card className="max-w-2xl overflow-hidden">
          <div className="flex items-start gap-4 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] px-6 py-5">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-[#0078d4]/10 text-[#0078d4]">
              <Mail className="h-5 w-5" aria-hidden />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="text-base font-semibold text-[var(--color-text)]">
                {t('integrations.outlook.title')}
              </h2>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                {t('integrations.outlook.description')}
              </p>
            </div>
          </div>

          <div className="space-y-4 p-6">
            {!available ? (
              <p className="text-sm text-[var(--color-text-muted)]" data-testid="outlook-unavailable">
                {t('integrations.outlook.notConfigured')}
              </p>
            ) : connected ? (
              <div className="space-y-3" data-testid="outlook-connected">
                <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
                  <p className="text-sm font-medium text-[var(--color-text)]">
                    {t('integrations.outlook.connectedAs')}
                  </p>
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">{status?.email}</p>
                  {scopesLabel ? (
                    <p className="mt-2 text-xs text-[var(--color-text-muted)]">
                      {t('integrations.outlook.scopes')}: {scopesLabel}
                    </p>
                  ) : null}
                </div>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('integrations.outlook.readOnlyNotice')}
                </p>
                <Button
                  variant="danger"
                  loading={disconnectMutation.isPending}
                  onClick={() => disconnectMutation.mutate()}
                  data-testid="outlook-disconnect"
                >
                  {t('integrations.outlook.disconnect')}
                </Button>
              </div>
            ) : (
              <div className="space-y-3" data-testid="outlook-disconnected">
                <p className="text-sm text-[var(--color-text-muted)]">
                  {t('integrations.outlook.disconnectedHint')}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {t('integrations.outlook.readOnlyNotice')}
                </p>
                <Button
                  type="button"
                  onClick={() => {
                    window.location.assign(outlookConnectUrl())
                  }}
                  data-testid="outlook-connect"
                >
                  {t('integrations.outlook.connect')}
                </Button>
              </div>
            )}
          </div>
        </Card>
      )}
    </div>
  )
}
