import { Check, Copy, Link2 } from 'lucide-react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { plansApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

type SharePlanPanelProps = {
  planId: string
  plan?: {
    shareEnabled?: boolean
    shareToken?: string | null
    status?: string
  }
}

export function buildShareUrl(shareToken: string): string {
  const origin = typeof window !== 'undefined' ? window.location.origin : ''
  return `${origin}/shared/plans/${shareToken}`
}

export function SharePlanPanel({ planId, plan }: SharePlanPanelProps) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [copied, setCopied] = useState(false)

  const shareMutation = useMutation({
    mutationFn: (shareEnabled: boolean) => plansApi.updateShare(planId, shareEnabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan', planId] })
    },
  })

  if (plan?.status === 'archived') return null

  const enabled = plan?.shareEnabled === true
  const shareUrl = plan?.shareToken ? buildShareUrl(plan.shareToken) : ''

  const copyLink = async () => {
    if (!shareUrl) return
    await navigator.clipboard.writeText(shareUrl)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 2000)
  }

  return (
    <Card>
      <div className="flex items-start gap-3">
        <Link2 className="mt-0.5 h-4 w-4 text-[var(--color-primary)]" />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold">{t('planner.shareTitle')}</h3>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">{t('planner.shareHint')}</p>

          <label className="mt-3 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              disabled={shareMutation.isPending}
              onChange={(e) => shareMutation.mutate(e.target.checked)}
              className="rounded border-[var(--color-border)]"
            />
            {t('planner.shareEnabled')}
          </label>

          {enabled && shareUrl ? (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <code className="max-w-full truncate rounded-lg bg-[var(--color-surface-muted)] px-2 py-1 text-xs">
                {shareUrl}
              </code>
              <Button variant="secondary" size="sm" onClick={copyLink}>
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {copied ? t('planner.linkCopied') : t('planner.copyLink')}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  )
}
