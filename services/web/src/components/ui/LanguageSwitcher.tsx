import { useId } from 'react'
import { Globe } from 'lucide-react'
import { useTranslation } from '../../i18n'
import type { Locale } from '../../i18n/types'
import { cn } from '../../lib/utils'

export function LanguageSwitcher({ className }: { className?: string }) {
  const { locale, setLocale, t } = useTranslation()
  const selectId = useId()

  const options: { id: Locale; label: string }[] = [
    { id: 'he', label: t('common.hebrew') },
    { id: 'en', label: t('common.english') },
  ]

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <Globe className="h-4 w-4 text-[var(--color-text-muted)]" aria-hidden />
      <label className="sr-only" htmlFor={selectId}>
        {t('common.language')}
      </label>
      <select
        id={selectId}
        value={locale}
        onChange={(e) => setLocale(e.target.value as Locale)}
        className="h-9 rounded-lg border border-[var(--color-border)] bg-white px-2 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
      >
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
