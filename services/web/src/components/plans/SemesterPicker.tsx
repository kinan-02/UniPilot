import { useTranslation } from '../../i18n'
import { semesterLabel, upcomingSemesterCodes } from '../../lib/semester'
import { cn } from '../../lib/utils'

type SemesterPickerProps = {
  value: string
  onChange: (code: string) => void
  error?: string
  compact?: boolean
}

export function SemesterPicker({ value, onChange, error, compact = false }: SemesterPickerProps) {
  const { t, locale } = useTranslation()
  const options = upcomingSemesterCodes(4)

  if (compact) {
    return (
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-[var(--color-text-muted)]">{t('common.semester')}:</span>
          {options.map((code) => {
            const selected = value === code
            return (
              <button
                key={code}
                type="button"
                title={code}
                onClick={() => onChange(code)}
                className={cn(
                  'rounded-lg border px-2.5 py-1 text-xs font-medium transition',
                  selected
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
                    : 'border-[var(--color-border)] bg-white text-[var(--color-text-muted)] hover:border-[var(--color-primary)]/30',
                )}
              >
                {semesterLabel(code, locale)}
              </button>
            )
          })}
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-lg border border-dashed border-[var(--color-border)] px-2.5 py-1 text-xs text-[var(--color-text-muted)] hover:border-[var(--color-primary)]/30 [&::-webkit-details-marker]:hidden">
              {t('plans.customSemesterCode')}
            </summary>
            <div className="absolute start-0 top-full z-10 mt-1 min-w-[140px] rounded-lg border border-[var(--color-border)] bg-white p-2 shadow-md">
              <input
                value={value}
                onChange={(e) => onChange(e.target.value)}
                placeholder="2025-2"
                className={cn(
                  'h-8 w-full rounded-md border bg-white px-2 font-mono text-xs',
                  'focus:border-[var(--color-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]/15',
                  error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
                )}
              />
            </div>
          </details>
        </div>
        {error ? <p className="text-xs text-[var(--color-danger)]">{error}</p> : null}
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-[var(--color-text)]">{t('plans.pickSemester')}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((code) => {
          const selected = value === code
          return (
            <button
              key={code}
              type="button"
              onClick={() => onChange(code)}
              className={cn(
                'rounded-xl border px-4 py-3 text-start text-sm transition',
                selected
                  ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5 text-[var(--color-primary)] shadow-sm'
                  : 'border-[var(--color-border)] bg-white hover:border-[var(--color-primary)]/30',
              )}
            >
              <span className="block font-semibold">{semesterLabel(code, locale)}</span>
              <span className="mt-0.5 block font-mono text-xs text-[var(--color-text-muted)]">{code}</span>
            </button>
          )
        })}
      </div>
      <label className="block space-y-1.5">
        <span className="text-xs text-[var(--color-text-muted)]">{t('plans.customSemesterCode')}</span>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="2025-2"
          className={cn(
            'h-10 w-full max-w-xs rounded-xl border bg-white px-3 font-mono text-sm',
            'focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
            error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
          )}
        />
      </label>
      {error ? <p className="text-xs text-[var(--color-danger)]">{error}</p> : null}
      <p className="text-xs text-[var(--color-text-muted)]">{t('plans.semesterAcademicYearHint')}</p>
    </div>
  )
}
