import { Badge, Card } from '../ui/Card'
import { useTranslation } from '../../i18n'
import { formatCreditDelta } from '../../lib/simulationMappers'
import { formatCredits } from '../../lib/utils'
import type { SimulationResult } from '../../types/api'

function CreditStat({
  label,
  before,
  after,
  delta,
}: {
  label: string
  before?: number
  after?: number
  delta?: number
}) {
  const deltaTone =
    delta === undefined || delta === 0 ? 'neutral' : delta > 0 ? 'success' : 'danger'

  return (
    <div className="rounded-xl bg-[var(--color-surface-muted)] px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
        {label}
      </p>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">Before</p>
          <p className="text-lg font-semibold">{formatCredits(before ?? 0)}</p>
        </div>
        <p className="text-[var(--color-text-muted)]">→</p>
        <div>
          <p className="text-xs text-[var(--color-text-muted)]">After</p>
          <p className="text-lg font-semibold">{formatCredits(after ?? 0)}</p>
        </div>
        {delta !== undefined ? (
          <Badge tone={deltaTone}>Δ {formatCreditDelta(delta)}</Badge>
        ) : null}
      </div>
    </div>
  )
}

export function SimulationResultPanel({ result }: { result: SimulationResult }) {
  const { t } = useTranslation()
  const before = result.beforeSnapshot.graduation
  const after = result.afterSnapshot.graduation
  const progressDelta = result.deltas.progress

  return (
    <Card className="border-[var(--color-primary)]/20" data-testid="simulation-result-panel">
      <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-primary)]">
        {t('simulations.latestResult')}
      </p>
      {result.summary ? <p className="mt-2 text-sm leading-relaxed">{result.summary}</p> : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <CreditStat
          label={t('simulations.completedCredits')}
          before={before?.completedCredits}
          after={after?.completedCredits}
          delta={progressDelta?.completedCreditsDelta}
        />
        <CreditStat
          label={t('simulations.creditsRemaining')}
          before={before?.creditsRemaining}
          after={after?.creditsRemaining}
          delta={progressDelta?.creditsRemainingDelta}
        />
      </div>

      {before?.completionPercentage !== undefined || after?.completionPercentage !== undefined ? (
        <p className="mt-4 text-sm text-[var(--color-text-muted)]">
          {t('simulations.completion')}: {before?.completionPercentage ?? 0}% →{' '}
          {after?.completionPercentage ?? 0}%
          {progressDelta?.completionPercentageDelta !== undefined
            ? ` (${formatCreditDelta(progressDelta.completionPercentageDelta)}%)`
            : ''}
        </p>
      ) : null}

      {result.warnings?.length ? (
        <ul className="mt-4 space-y-2">
          {result.warnings.map((warning) => (
            <li
              key={warning}
              className="rounded-xl border border-[var(--color-warning)]/30 bg-[var(--color-warning)]/5 px-4 py-2 text-sm"
            >
              {warning}
            </li>
          ))}
        </ul>
      ) : null}

      {result.narrative ? (
        <details className="mt-4 rounded-xl border border-dashed border-[var(--color-border)] bg-white p-3 text-sm">
          <summary className="cursor-pointer font-medium text-[var(--color-text)]">
            {t('simulations.narrativeTitle')}
          </summary>
          <p className="mt-2 whitespace-pre-wrap leading-relaxed text-[var(--color-text-muted)]">
            {result.narrative}
          </p>
          <p className="mt-2 text-xs text-[var(--color-text-muted)]">{t('simulations.narrativeHint')}</p>
        </details>
      ) : null}
    </Card>
  )
}
