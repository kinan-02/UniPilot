import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FlaskConical, Play, Sparkles } from 'lucide-react'
import { simulationsApi } from '../api/endpoints'
import { SimulationResultPanel } from '../components/simulations/SimulationResultPanel'
import { Button } from '../components/ui/Button'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { useSimulationAsyncJob } from '../hooks/useSimulationAsyncJob'
import { useTranslation } from '../i18n'
import { formatOperationLabel } from '../lib/simulationMappers'
import type { SimulationResult, SimulationScenario } from '../types/api'

export function SimulationsPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const [scenarioText, setScenarioText] = useState(() => searchParams.get('text') ?? '')
  const [activeScenarioId, setActiveScenarioId] = useState<string | null>(null)
  const [activeResult, setActiveResult] = useState<SimulationResult | null>(null)
  const [pendingJobId, setPendingJobId] = useState<string | null>(null)
  const [handledJobId, setHandledJobId] = useState<string | null>(null)
  const [preferInstant, setPreferInstant] = useState(false)

  const planIdFromUrl = searchParams.get('planId') ?? undefined
  const autoBuildFromUrl = searchParams.get('autoBuild') === '1'
  const deepLinkHandled = useRef(false)
  const asyncJob = useSimulationAsyncJob(pendingJobId)

  const scenariosQuery = useQuery({
    queryKey: ['simulation-scenarios'],
    queryFn: async () => {
      const data = await simulationsApi.list()
      return data.simulationScenarios
    },
  })

  const activeScenarioQuery = useQuery({
    queryKey: ['simulation-scenario', activeScenarioId],
    queryFn: async () => {
      if (!activeScenarioId) {
        return null
      }
      const data = await simulationsApi.get(activeScenarioId)
      return data.simulationScenario
    },
    enabled: Boolean(activeScenarioId),
  })

  const resultsQuery = useQuery({
    queryKey: ['simulation-results', activeScenarioId],
    queryFn: async () => {
      if (!activeScenarioId) {
        return []
      }
      const data = await simulationsApi.listResults(activeScenarioId)
      return data.simulationResults
    },
    enabled: Boolean(activeScenarioId),
  })

  const activeScenario: SimulationScenario | null = activeScenarioQuery.data ?? null
  const historyResults = resultsQuery.data ?? []
  const displayedResult = activeResult ?? historyResults[0] ?? null

  const fromTextMutation = useMutation({
    mutationFn: (text: string) =>
      simulationsApi.createFromText({
        text,
        planId: planIdFromUrl,
      }),
    onSuccess: (data) => {
      setActiveScenarioId(data.simulationScenario.id)
      setActiveResult(null)
      setPendingJobId(null)
      setHandledJobId(null)
      void queryClient.invalidateQueries({ queryKey: ['simulation-scenarios'] })
      void queryClient.invalidateQueries({
        queryKey: ['simulation-scenario', data.simulationScenario.id],
      })
    },
  })

  const runMutation = useMutation({
    mutationFn: (scenarioId: string) =>
      simulationsApi.run(scenarioId, preferInstant ? 'sync' : 'auto'),
    onSuccess: (data, scenarioId) => {
      if (data.asyncAccepted) {
        setPendingJobId(data.job.id)
        setHandledJobId(null)
        return
      }

      setActiveResult(data.simulationResult)
      void queryClient.invalidateQueries({ queryKey: ['simulation-results', scenarioId] })
    },
  })

  useEffect(() => {
    const textFromUrl = searchParams.get('text')?.trim()
    if (!autoBuildFromUrl || !textFromUrl || deepLinkHandled.current) {
      return
    }
    deepLinkHandled.current = true
    fromTextMutation.mutate(textFromUrl)
  }, [autoBuildFromUrl, fromTextMutation, searchParams])

  useEffect(() => {
    if (!pendingJobId || !asyncJob.job || handledJobId === pendingJobId) {
      return
    }

    if (asyncJob.job.status === 'completed' && asyncJob.simulationResult) {
      setActiveResult(asyncJob.simulationResult)
      void queryClient.invalidateQueries({
        queryKey: ['simulation-results', asyncJob.simulationResult.scenarioId],
      })
      setHandledJobId(pendingJobId)
      setPendingJobId(null)
    }

    if (asyncJob.job.status === 'failed') {
      setHandledJobId(pendingJobId)
      setPendingJobId(null)
    }
  }, [
    asyncJob.job,
    asyncJob.simulationResult,
    handledJobId,
    pendingJobId,
    queryClient,
  ])

  const suggestedPrompts = useMemo(
    () => [
      t('simulations.promptDrop'),
      t('simulations.promptPlan'),
      t('simulations.promptTrack'),
    ],
    [t],
  )

  const isBusy = fromTextMutation.isPending || runMutation.isPending || asyncJob.isPolling

  const buildScenario = (text?: string) => {
    const trimmed = (text ?? scenarioText).trim()
    if (!trimmed || isBusy) {
      return
    }
    fromTextMutation.mutate(trimmed)
  }

  const handleBuildSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    buildScenario()
  }

  const selectScenario = (scenarioId: string) => {
    setActiveScenarioId(scenarioId)
    setActiveResult(null)
    setPendingJobId(null)
    setHandledJobId(null)
  }

  const startNewScenario = () => {
    setActiveScenarioId(null)
    setActiveResult(null)
    setScenarioText('')
    setPendingJobId(null)
    setHandledJobId(null)
  }

  const jobStatusMessage =
    asyncJob.job?.status === 'pending'
      ? t('simulations.jobStatusPending')
      : asyncJob.job?.status === 'processing'
        ? t('simulations.jobStatusProcessing')
        : null

  const showJobError =
    asyncJob.isError ||
    (asyncJob.job?.status === 'failed' && handledJobId !== asyncJob.job.id)

  const scenarios = scenariosQuery.data ?? []

  return (
    <div className="animate-fade-in space-y-6" data-testid="simulations-page">
      <PageHeader title={t('simulations.title')} description={t('simulations.subtitle')} />

      <div className="grid gap-6 lg:grid-cols-[minmax(240px,280px)_1fr]">
        <Card className="h-fit space-y-3 p-4" data-testid="simulation-history">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">{t('simulations.historyTitle')}</h2>
            <Button
              type="button"
              variant="secondary"
              className="h-8 px-2 text-xs"
              onClick={startNewScenario}
              data-testid="simulation-new"
            >
              {t('simulations.newScenario')}
            </Button>
          </div>

          {scenariosQuery.isLoading ? (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          ) : scenarios.length ? (
            <ul className="space-y-2">
              {scenarios.map((scenario) => (
                <li key={scenario.id}>
                  <button
                    type="button"
                    onClick={() => selectScenario(scenario.id)}
                    className={`w-full rounded-xl border px-3 py-2 text-start text-sm transition-colors ${
                      activeScenarioId === scenario.id
                        ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5'
                        : 'border-[var(--color-border)] hover:bg-[var(--color-surface-muted)]'
                    }`}
                  >
                    <p className="font-medium">{scenario.name}</p>
                    <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
                      {scenario.operations.length} {t('simulations.operations')}
                    </p>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-[var(--color-text-muted)]">{t('simulations.noHistory')}</p>
          )}
        </Card>

        <div className="space-y-6">
          <Card className="space-y-4">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                <FlaskConical className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold">{t('simulations.builderTitle')}</p>
                <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                  {t('simulations.builderHint')}
                </p>
              </div>
            </div>

            <form onSubmit={handleBuildSubmit} className="space-y-3">
              <label className="block text-sm font-medium" htmlFor="simulation-text">
                {t('simulations.inputLabel')}
              </label>
              <textarea
                id="simulation-text"
                data-testid="simulation-text"
                value={scenarioText}
                onChange={(event) => setScenarioText(event.target.value)}
                placeholder={t('simulations.inputPlaceholder')}
                rows={4}
                className="w-full rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 text-sm outline-none focus:border-[var(--color-primary)] focus:ring-2 focus:ring-[var(--color-primary)]/20"
              />

              <div className="flex flex-wrap gap-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => {
                      setScenarioText(prompt)
                      buildScenario(prompt)
                    }}
                    className="rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-text)]"
                  >
                    <Sparkles className="me-1 inline h-3 w-3" />
                    {prompt}
                  </button>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <Button
                  type="submit"
                  loading={fromTextMutation.isPending}
                  disabled={!scenarioText.trim() || isBusy}
                  data-testid="simulation-build"
                >
                  {t('simulations.buildScenario')}
                </Button>
                <label className="flex items-center gap-2 text-sm text-[var(--color-text-muted)]">
                  <input
                    type="checkbox"
                    checked={preferInstant}
                    onChange={(event) => setPreferInstant(event.target.checked)}
                    data-testid="simulation-prefer-instant"
                  />
                  {t('simulations.preferInstant')}
                </label>
              </div>
            </form>

            {fromTextMutation.isError ? (
              <p className="text-sm text-[var(--color-danger)]">
                {(fromTextMutation.error as Error).message}
              </p>
            ) : null}
          </Card>

          {activeScenario ? (
            <Card className="space-y-4" data-testid="simulation-active-scenario">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                    {t('simulations.activeScenario')}
                  </p>
                  <h2 className="mt-1 text-lg font-semibold">{activeScenario.name}</h2>
                  {activeScenario.description ? (
                    <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                      {activeScenario.description}
                    </p>
                  ) : null}
                </div>
                <Button
                  type="button"
                  loading={runMutation.isPending || asyncJob.isPolling}
                  disabled={isBusy}
                  onClick={() => runMutation.mutate(activeScenario.id)}
                  data-testid="simulation-run"
                >
                  <Play className="h-4 w-4" />
                  {t('simulations.run')}
                </Button>
              </div>

              <div className="flex flex-wrap gap-2">
                {activeScenario.operations.map((operation, index) => (
                  <Badge key={`${operation.type}-${index}`} tone="primary">
                    {formatOperationLabel(operation)}
                  </Badge>
                ))}
              </div>

              {asyncJob.isPolling && jobStatusMessage ? (
                <div className="flex items-center gap-2 rounded-xl bg-[var(--color-surface-muted)] px-4 py-3 text-sm">
                  <Spinner />
                  <span>{jobStatusMessage}</span>
                </div>
              ) : null}

              {showJobError ? (
                <p className="text-sm text-[var(--color-danger)]">
                  {asyncJob.job?.error ?? t('simulations.runError')}
                  {asyncJob.job?.status === 'failed' ? ` ${t('simulations.jobStatusFailed')}` : ''}
                </p>
              ) : null}

              {runMutation.isError ? (
                <p className="text-sm text-[var(--color-danger)]">
                  {(runMutation.error as Error).message}
                </p>
              ) : null}
            </Card>
          ) : (
            <EmptyState
              title={t('simulations.emptyTitle')}
              description={t('simulations.emptyDescription')}
            />
          )}

          {displayedResult ? <SimulationResultPanel result={displayedResult} /> : null}

          {historyResults.length > 1 ? (
            <Card>
              <h2 className="mb-4 text-sm font-semibold">{t('simulations.pastResults')}</h2>
              <div className="divide-y divide-[var(--color-border)]">
                {historyResults.slice(1).map((result) => (
                  <button
                    key={result.id}
                    type="button"
                    onClick={() => setActiveResult(result)}
                    className="w-full py-3 text-start first:pt-0 last:pb-0 hover:text-[var(--color-primary)]"
                  >
                    <p className="text-sm">{result.summary ?? t('simulations.resultFallback')}</p>
                    <p className="text-xs text-[var(--color-text-muted)]">
                      {result.generatedAt ?? result.createdAt ?? '—'}
                    </p>
                  </button>
                ))}
              </div>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  )
}
