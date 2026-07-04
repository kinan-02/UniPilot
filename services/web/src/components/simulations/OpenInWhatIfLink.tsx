import { Link } from 'react-router-dom'
import { FlaskConical } from 'lucide-react'
import { useTranslation } from '../../i18n'
import { buildSimulationPath } from '../../lib/simulationLinks'
import { cn } from '../../lib/utils'

type OpenInWhatIfLinkProps = {
  text: string
  planId?: string
  autoBuild?: boolean
  className?: string
  variant?: 'inline' | 'button'
  testId?: string
}

export function OpenInWhatIfLink({
  text,
  planId,
  autoBuild = true,
  className,
  variant = 'inline',
  testId = 'open-in-what-if',
}: OpenInWhatIfLinkProps) {
  const { t } = useTranslation()
  const to = buildSimulationPath({ text, planId, autoBuild })

  if (variant === 'button') {
    return (
      <Link
        to={to}
        data-testid={testId}
        className={cn(
          'inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium transition hover:border-[var(--color-primary)]/30 hover:bg-[var(--color-surface-muted)]',
          className,
        )}
      >
        <FlaskConical className="h-4 w-4 text-[var(--color-primary)]" aria-hidden />
        {t('simulations.openInWhatIf')}
      </Link>
    )
  }

  return (
    <Link
      to={to}
      data-testid={testId}
      className={cn(
        'inline-flex items-center gap-1 font-medium text-[var(--color-primary)] hover:underline',
        className,
      )}
    >
      <FlaskConical className="h-3.5 w-3.5" aria-hidden />
      {t('simulations.openInWhatIf')}
    </Link>
  )
}
