import { useQuery } from '@tanstack/react-query'
import { progressApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { formatCredits, formatPercent } from '../lib/utils'

export function ProgressPage() {
  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: progressApi.get,
    retry: false,
  })

  if (progressQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  if (progressQuery.isError) {
    const message =
      isAuthError(progressQuery.error) && progressQuery.error.status === 400
        ? 'Select a degree program in your profile to calculate graduation progress.'
        : 'Unable to load graduation progress.'
    return (
      <EmptyState title="Progress unavailable" description={message} action={null} />
    )
  }

  const progress = progressQuery.data?.graduationProgress
  if (!progress) return null

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title="Graduation progress"
        description={progress.degreeName ?? progress.degreeCode ?? 'Your degree track'}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <div className="mb-4 flex items-end justify-between">
            <div>
              <p className="text-sm text-[var(--color-text-muted)]">Overall completion</p>
              <p className="text-4xl font-semibold tracking-tight">
                {formatPercent(progress.completionPercentage)}
              </p>
            </div>
            <Badge tone={progress.statusSummary === 'complete' ? 'success' : 'primary'}>
              {progress.statusSummary.replace(/_/g, ' ')}
            </Badge>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-stone-100">
            <div
              className="h-full rounded-full bg-[var(--color-primary)] transition-all duration-500"
              style={{ width: `${Math.min(progress.completionPercentage, 100)}%` }}
            />
          </div>
          <p className="mt-3 text-sm text-[var(--color-text-muted)]">
            {formatCredits(progress.completedCredits)} completed ·{' '}
            {formatCredits(progress.creditsRemaining)} remaining ·{' '}
            {formatCredits(progress.totalRequiredCredits)} required
          </p>
        </Card>
        <Card>
          <p className="text-sm font-medium">Quick stats</p>
          <dl className="mt-4 space-y-3 text-sm">
            <div className="flex justify-between">
              <dt className="text-[var(--color-text-muted)]">Degree ID</dt>
              <dd className="font-mono text-xs">{progress.degreeId.slice(-8)}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-[var(--color-text-muted)]">Status</dt>
              <dd>{progress.statusSummary.replace(/_/g, ' ')}</dd>
            </div>
          </dl>
        </Card>
      </div>

      {progress.requirementProgress?.length ? (
        <Card>
          <h2 className="mb-4 text-sm font-semibold">Requirement buckets</h2>
          <div className="space-y-4">
            {progress.requirementProgress.map((bucket) => (
              <div key={bucket.requirementGroupId}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{bucket.title ?? bucket.requirementGroupId}</span>
                  <span className="text-[var(--color-text-muted)]">
                    {formatCredits(bucket.completedCredits)} / {formatCredits(bucket.requiredCredits)}
                  </span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)]"
                    style={{
                      width: `${Math.min(
                        (bucket.completedCredits / Math.max(bucket.requiredCredits, 1)) * 100,
                        100,
                      )}%`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  )
}
