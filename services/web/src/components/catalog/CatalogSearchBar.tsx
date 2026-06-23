import { useEffect, useRef } from 'react'
import { Clock, Search, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { CatalogQuickFilters } from './CatalogQuickFilters'
import type { CatalogCreditBand } from '../../lib/catalog'

type CatalogSearchBarProps = {
  query: string
  faculty: string
  creditBand: CatalogCreditBand
  faculties: string[]
  facultiesLoading?: boolean
  recentSearches: string[]
  t: (key: string) => string
  onQueryChange: (value: string) => void
  onFacultyChange: (value: string) => void
  onCreditBandChange: (band: CatalogCreditBand) => void
  onRecentSelect: (value: string) => void
  onClearRecent: () => void
  onClear: () => void
}

export function CatalogSearchBar({
  query,
  faculty,
  creditBand,
  faculties,
  facultiesLoading,
  recentSearches,
  t,
  onQueryChange,
  onFacultyChange,
  onCreditBandChange,
  onRecentSelect,
  onClearRecent,
  onClear,
}: CatalogSearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const hasFilters = Boolean(query.trim() || faculty || creditBand !== 'all')

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return
      }
      event.preventDefault()
      inputRef.current?.focus()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  return (
    <Card className="mb-4 space-y-4" data-testid="catalog-search-bar">
      <div className="grid gap-4 lg:grid-cols-[1fr_240px_auto] lg:items-end">
        <div className="relative">
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            ref={inputRef}
            type="search"
            className={cn(
              'h-11 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-3 text-sm',
              'placeholder:text-[var(--color-text-muted)]/70',
              'transition-colors focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
            )}
            placeholder={t('catalog.searchPlaceholder')}
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            data-testid="catalog-search-input"
          />
        </div>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t('catalog.faculty')}</span>
          <select
            value={faculty}
            onChange={(event) => onFacultyChange(event.target.value)}
            disabled={facultiesLoading}
            data-testid="catalog-faculty-select"
            className="h-11 w-full rounded-xl border border-[var(--color-border)] bg-white px-3.5 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15 disabled:opacity-60"
          >
            <option value="">{t('catalog.allFaculties')}</option>
            {faculties.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        {hasFilters ? (
          <Button variant="secondary" size="md" onClick={onClear} className="h-11">
            <X className="h-4 w-4" />
            {t('catalog.clearFilters')}
          </Button>
        ) : (
          <div className="hidden lg:block" aria-hidden />
        )}
      </div>

      <CatalogQuickFilters creditBand={creditBand} t={t} onCreditBandChange={onCreditBandChange} />

      {!query.trim() && recentSearches.length ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--color-text-muted)]">
            <Clock className="h-3.5 w-3.5" />
            {t('catalog.recentSearches')}
          </span>
          {recentSearches.map((entry) => (
            <button
              key={entry}
              type="button"
              onClick={() => onRecentSelect(entry)}
              className="rounded-full border border-[var(--color-border)] bg-white px-3 py-1 text-xs font-medium transition hover:border-[var(--color-primary)]/30"
            >
              {entry}
            </button>
          ))}
          <button
            type="button"
            onClick={onClearRecent}
            className="text-xs text-[var(--color-text-muted)] underline-offset-2 hover:underline"
          >
            {t('catalog.clearRecent')}
          </button>
        </div>
      ) : null}

      <p className="text-xs text-[var(--color-text-muted)]">
        {t('catalog.searchHint')} · {t('catalog.focusSearchHint')}
      </p>
    </Card>
  )
}
