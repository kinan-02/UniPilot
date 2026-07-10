import { useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Bell, Route, ShieldAlert, X } from 'lucide-react'
import { Link } from 'react-router-dom'
import { recommendationsApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import {
  RECOMMENDATIONS_QUERY_KEY,
  useRecommendationsQuery,
} from '../../lib/recommendationsQuery'
import { buildWatchdogLink } from '../../lib/watchdogLinks'
import { hasStudentProfile, useStudentProfileQuery } from '../../lib/studentProfileQuery'
import { cn } from '../../lib/utils'
import type { AiRecommendation } from '../../types/api'
import { Badge, Card, Spinner } from '../ui/Card'
import { Button } from '../ui/Button'

function nudgeIcon(nudgeType: string | null | undefined) {
  if (nudgeType === 'prereq') return Route
  if (nudgeType === 'risk') return ShieldAlert
  return AlertTriangle
}

function severityTone(severity: string | null | undefined): 'warning' | 'danger' | 'neutral' {
  if (severity === 'high') return 'danger'
  if (severity === 'medium') return 'warning'
  return 'neutral'
}

function WatchdogNudgeItem({
  recommendation,
  onDismiss,
  dismissing,
}: {
  recommendation: AiRecommendation
  onDismiss: (id: string) => void
  dismissing: boolean
}) {
  const { t } = useTranslation()
  const nudgeType = recommendation.nudgeType ?? recommendation.type
  const Icon = nudgeIcon(nudgeType)
  const action = buildWatchdogLink(recommendation)

  return (
    <li
      className="rounded-xl border border-[var(--color-border)] bg-white p-4"
      data-testid={`watchdog-nudge-${recommendation.id}`}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
            severityTone(recommendation.severity) === 'danger' && 'bg-red-50 text-red-700',
            severityTone(recommendation.severity) === 'warning' && 'bg-amber-50 text-amber-800',
            severityTone(recommendation.severity) === 'neutral' && 'bg-stone-100 text-stone-700',
          )}
        >
          <Icon className="h-4 w-4" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-[var(--color-text)]">{recommendation.title}</p>
            <Badge tone={severityTone(recommendation.severity)}>
              {t(`watchdog.severity.${recommendation.severity ?? 'medium'}`)}
            </Badge>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-muted)]">
            {recommendation.body}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link
              to={action.to}
              className="inline-flex items-center rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-xs font-medium text-white transition hover:opacity-90"
            >
              {t(action.labelKey)}
            </Link>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              disabled={dismissing}
              onClick={() => onDismiss(recommendation.id)}
              className="text-xs"
            >
              {t('watchdog.dismiss')}
            </Button>
          </div>
        </div>
        <button
          type="button"
          className="rounded-lg p-1 text-[var(--color-text-muted)] transition hover:bg-[var(--color-surface-muted)]"
          aria-label={t('watchdog.dismiss')}
          disabled={dismissing}
          onClick={() => onDismiss(recommendation.id)}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </li>
  )
}

export function WatchdogNudgesCard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const profileQuery = useStudentProfileQuery()
  const enabled = hasStudentProfile(profileQuery.data)
  const recommendationsQuery = useRecommendationsQuery(enabled)

  const dismissMutation = useMutation({
    mutationFn: (recommendationId: string) => recommendationsApi.dismiss(recommendationId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: RECOMMENDATIONS_QUERY_KEY })
    },
  })

  if (!enabled) return null

  if (recommendationsQuery.isLoading) {
    return (
      <Card className="flex items-center gap-3 py-5" data-testid="watchdog-nudges-loading">
        <Spinner />
        <p className="text-sm text-[var(--color-text-muted)]">{t('watchdog.loading')}</p>
      </Card>
    )
  }

  if (recommendationsQuery.isError) return null

  const recommendations = recommendationsQuery.data?.recommendations ?? []
  if (recommendations.length === 0) {
    return (
      <Card
        id="watchdog-nudges"
        className="scroll-mt-24 border-dashed bg-[var(--color-surface-muted)]/40 px-5 py-4"
        data-testid="watchdog-nudges-empty"
      >
        <div className="flex items-start gap-3">
          <Bell className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-text-muted)]" aria-hidden />
          <div>
            <p className="text-sm font-medium text-[var(--color-text)]">{t('watchdog.emptyTitle')}</p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-text-muted)]">
              {t('watchdog.emptySubtitle')}
            </p>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <Card
      id="watchdog-nudges"
      className="scroll-mt-24 space-y-4 p-0 overflow-hidden"
      data-testid="watchdog-nudges-card"
    >
      <div className="flex items-center gap-3 border-b border-[var(--color-border)] bg-gradient-to-r from-sky-50/80 via-white to-white px-5 py-4">
        <Bell className="h-5 w-5 shrink-0 text-sky-700" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{t('watchdog.title')}</p>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{t('watchdog.subtitle')}</p>
        </div>
        <Badge tone="primary">{recommendations.length}</Badge>
      </div>
      <ul className="space-y-3 px-5 pb-5">
        {recommendations.map((recommendation) => (
          <WatchdogNudgeItem
            key={recommendation.id}
            recommendation={recommendation}
            onDismiss={(id) => dismissMutation.mutate(id)}
            dismissing={dismissMutation.isPending}
          />
        ))}
      </ul>
    </Card>
  )
}

export function useActiveRecommendationCount(): number {
  const profileQuery = useStudentProfileQuery()
  const recommendationsQuery = useRecommendationsQuery(hasStudentProfile(profileQuery.data))
  return recommendationsQuery.data?.recommendations.length ?? 0
}
