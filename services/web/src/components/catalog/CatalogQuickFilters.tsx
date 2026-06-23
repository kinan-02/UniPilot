import { BookOpen, Filter } from 'lucide-react'
import { Card } from '../ui/Card'
import type { CatalogCreditBand } from '../../lib/catalog'

type CatalogQuickFiltersProps = {
  creditBand: CatalogCreditBand
  t: (key: string) => string
  onCreditBandChange: (band: CatalogCreditBand) => void
}

const BANDS: CatalogCreditBand[] = ['all', 'low', 'mid', 'high']

export function CatalogQuickFilters({
  creditBand,
  t,
  onCreditBandChange,
}: CatalogQuickFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="catalog-quick-filters">
      <span className="inline-flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
        <Filter className="h-3.5 w-3.5" />
        {t('catalog.creditsFilter')}
      </span>
      {BANDS.map((band) => {
        const active = creditBand === band
        return (
          <button
            key={band}
            type="button"
            data-testid={`catalog-credit-band-${band}`}
            onClick={() => onCreditBandChange(band)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
              active
                ? 'bg-[var(--color-primary)] text-white shadow-sm'
                : 'border border-[var(--color-border)] bg-white text-[var(--color-text-muted)] hover:border-[var(--color-primary)]/30 hover:text-[var(--color-text)]'
            }`}
          >
            {t(`catalog.creditBands.${band}`)}
          </button>
        )
      })}
    </div>
  )
}

type CatalogStatsBarProps = {
  total: number
  visible: number
  isFetching: boolean
  t: (key: string) => string
}

export function CatalogStatsBar({ total, visible, isFetching, t }: CatalogStatsBarProps) {
  return (
    <Card
      className="mb-4 flex flex-wrap items-center justify-between gap-3 border-[var(--color-primary)]/10 bg-gradient-to-r from-white to-[var(--color-surface-muted)]/70 px-4 py-3"
      data-testid="catalog-stats-bar"
    >
      <div className="flex items-center gap-2 text-sm">
        <BookOpen className="h-4 w-4 text-[var(--color-primary)]" />
        <span className="font-medium">{t('catalog.statsTitle')}</span>
        <span className="text-[var(--color-text-muted)]">
          {t('catalog.statsSummary')
            .replace('{visible}', String(visible))
            .replace('{total}', String(total))}
        </span>
      </div>
      {isFetching ? (
        <span className="text-xs text-[var(--color-text-muted)]">{t('catalog.updatingResults')}</span>
      ) : null}
    </Card>
  )
}
