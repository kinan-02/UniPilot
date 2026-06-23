import { Check } from 'lucide-react'
import type { CatalogPathOption } from '../../types/api'
import { useTranslation } from '../../i18n'
import { optionLabel, pathOptionSubtitle } from '../../lib/profilePrograms'
import { cn } from '../../lib/utils'

type PathOptionCardProps = {
  option: CatalogPathOption
  selected: boolean
  onSelect: () => void
  mode?: 'radio' | 'checkbox'
  name?: string
}

export function PathOptionCard({
  option,
  selected,
  onSelect,
  mode = 'radio',
  name,
}: PathOptionCardProps) {
  const { locale } = useTranslation()
  const subtitle = pathOptionSubtitle(option, locale)

  return (
    <label
      className={cn(
        'group relative flex cursor-pointer gap-3 rounded-2xl border p-4 transition-all',
        selected
          ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5 shadow-[var(--shadow-card)]'
          : 'border-[var(--color-border)] bg-white hover:border-[var(--color-primary)]/40',
      )}
    >
      <input
        type={mode === 'checkbox' ? 'checkbox' : 'radio'}
        name={name}
        className="sr-only"
        checked={selected}
        onChange={onSelect}
      />
      <span
        className={cn(
          'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border',
          selected
            ? 'border-[var(--color-primary)] bg-[var(--color-primary)] text-white'
            : 'border-[var(--color-border)] bg-white text-transparent',
        )}
        aria-hidden="true"
      >
        <Check className="h-3 w-3" />
      </span>
      <span className="min-w-0 flex-1" dir={locale === 'he' ? 'rtl' : 'ltr'} lang={locale}>
        <span className="block text-sm font-semibold leading-snug text-[var(--color-text)]">
          {optionLabel(option, locale)}
        </span>
        {subtitle ? (
          <span className="mt-1 block text-xs text-[var(--color-text-muted)]">{subtitle}</span>
        ) : null}
      </span>
    </label>
  )
}
