import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { plansApi, risksApi } from '../api/endpoints'
import { Button } from '../components/ui/Button'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'

export function RisksPage() {
  const queryClient = useQueryClient()

  const risksQuery = useQuery({
    queryKey: ['risks'],
    queryFn: risksApi.list,
  })

  const plansQuery = useQuery({
    queryKey: ['plans'],
    queryFn: plansApi.list,
  })

  const analyzeMutation = useMutation({
    mutationFn: () => {
      const planId = plansQuery.data?.semesterPlans.find((p) => p.status !== 'archived')?.id
      if (!planId) {
        throw new Error('Create a semester plan before running risk analysis.')
      }
      return risksApi.analyze(planId)
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['risks'] }),
  })

  const analyses = risksQuery.data?.academicRiskAnalyses ?? []
  const latest = analyzeMutation.data?.academicRiskAnalysis

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title="Academic risks"
        description="Deterministic analysis of workload, prerequisites, and graduation gaps — no AI required."
        action={
          <Button
            loading={analyzeMutation.isPending}
            disabled={!plansQuery.data?.semesterPlans.length}
            onClick={() => analyzeMutation.mutate()}
          >
            Run analysis
          </Button>
        }
      />

      {analyzeMutation.isError ? (
        <p className="text-sm text-[var(--color-danger)]">
          {(analyzeMutation.error as Error).message}
        </p>
      ) : null}

      {latest ? (
        <Card className="border-[var(--color-primary)]/20">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-primary)]">
            Latest analysis
          </p>
          <p className="mt-2 text-sm">{latest.summary ?? 'Analysis complete'}</p>
          {latest.risks?.length ? (
            <ul className="mt-4 space-y-3">
              {latest.risks.map((risk, index) => (
                <li
                  key={risk.ruleId ?? index}
                  className="rounded-xl bg-[var(--color-surface-muted)] px-4 py-3"
                >
                  <div className="flex items-center gap-2">
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
                    <span className="text-sm font-medium">{risk.title ?? 'Finding'}</span>
                  </div>
                  <p className="mt-1 text-sm text-[var(--color-text-muted)]">{risk.message}</p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[var(--color-success)]">No significant risks detected.</p>
          )}
        </Card>
      ) : null}

      {risksQuery.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : analyses.length ? (
        <Card>
          <h2 className="mb-4 text-sm font-semibold">History</h2>
          <div className="divide-y divide-[var(--color-border)]">
            {analyses.map((analysis) => (
              <div key={analysis.id} className="py-3 first:pt-0 last:pb-0">
                <p className="text-sm">{analysis.summary ?? 'Risk analysis'}</p>
                <p className="text-xs text-[var(--color-text-muted)]">
                  {analysis.semesterCode ?? '—'} · {analysis.status}
                </p>
              </div>
            ))}
          </div>
        </Card>
      ) : (
        <EmptyState
          title="No analyses yet"
          description="Run your first academic risk analysis to identify scheduling and graduation gaps."
        />
      )}
    </div>
  )
}
