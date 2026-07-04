import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { plansApi, risksApi } from '../api/endpoints'
import { OpenInWhatIfLink } from '../components/simulations/OpenInWhatIfLink'
import { Button } from '../components/ui/Button'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { formatAcademicRiskSummary } from '../lib/academicRiskDisplay'
import { buildRiskMitigationText } from '../lib/simulationLinks'

export function RisksPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()

  const risksQuery = useQuery({
    queryKey: ['risks'],
    queryFn: risksApi.list,
  })

  const plansQuery = useQuery({
    queryKey: ['plans'],
    queryFn: plansApi.list,
  })

  const semesterPlans = plansQuery.data?.semesterPlans ?? []
  const activePlanId = semesterPlans.find((plan) => plan.status !== 'archived')?.id
  const analyses = risksQuery.data?.academicRiskAnalyses ?? []

  const analyzeMutation = useMutation({
    mutationFn: () => {
      if (!activePlanId) {
        throw new Error(t('risks.needPlan'))
      }
      return risksApi.analyze(activePlanId)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['risks'] }),
  })

  const latest = analyzeMutation.data?.academicRiskAnalysis
  const isInitialLoading = risksQuery.isLoading || plansQuery.isLoading

  return (
    <div className="animate-fade-in space-y-6" data-testid="risks-page">
      <PageHeader
        title={t('risks.title')}
        description={t('risks.subtitle')}
        action={
          <Button
            loading={analyzeMutation.isPending}
            disabled={!semesterPlans.length || plansQuery.isLoading}
            onClick={() => analyzeMutation.mutate()}
          >
            {t('risks.runAnalysis')}
          </Button>
        }
      />

      {plansQuery.isError ? (
        <p className="text-sm text-[var(--color-danger)]">
          {(plansQuery.error as Error).message}
        </p>
      ) : null}

      {risksQuery.isError ? (
        <p className="text-sm text-[var(--color-danger)]">
          {(risksQuery.error as Error).message}
        </p>
      ) : null}

      {analyzeMutation.isError ? (
        <p className="text-sm text-[var(--color-danger)]">
          {(analyzeMutation.error as Error).message}
        </p>
      ) : null}

      {latest ? (
        <Card className="border-[var(--color-primary)]/20">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-primary)]">
            {t('risks.latestAnalysis')}
          </p>
          <p className="mt-2 text-sm">
            {formatAcademicRiskSummary(latest.summary, t, t('risks.analysisComplete'))}
          </p>
          {latest.risks?.length ? (
            <ul className="mt-4 space-y-3">
              {latest.risks.map((risk, index) => (
                <li
                  key={risk.ruleId ?? `${risk.title ?? 'risk'}-${index}`}
                  className="rounded-xl bg-[var(--color-surface-muted)] px-4 py-3"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      tone={
                        risk.severity === 'high'
                          ? 'danger'
                          : risk.severity === 'medium'
                            ? 'warning'
                            : 'neutral'
                      }
                    >
                      {risk.severity ?? 'info'}
                    </Badge>
                    <span className="text-sm font-medium">{risk.title ?? t('risks.finding')}</span>
                  </div>
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">{risk.message}</p>
                  <div className="mt-2">
                    <OpenInWhatIfLink
                      text={buildRiskMitigationText(risk, activePlanId)}
                      planId={activePlanId}
                      testId={`risk-simulate-${risk.ruleId ?? index}`}
                    />
                  </div>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[var(--color-success)]">{t('risks.noSignificantRisks')}</p>
          )}
        </Card>
      ) : null}

      {isInitialLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : analyses.length ? (
        <Card>
          <h2 className="mb-4 text-sm font-semibold">{t('risks.history')}</h2>
          <div className="divide-y divide-[var(--color-border)]">
            {analyses.map((analysis) => (
              <div key={analysis.id} className="py-3 first:pt-0 last:pb-0">
                <p className="text-sm">
                  {formatAcademicRiskSummary(analysis.summary, t, t('risks.analysisFallback'))}
                </p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {analysis.semesterCode ?? '—'} · {analysis.status}
                </p>
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <EmptyState
          title={t('risks.emptyTitle')}
          description={t('risks.emptyDescription')}
        />
      )}
    </div>
  )
}
