import { useTranslation } from '../../i18n'
import { semesterLabel, upcomingSemesterCodes } from '../../lib/semester'
import { cn } from '../../lib/utils'

type SemesterPickerProps = {
  value: string
  onChange: (code: string) => void
  error?: string
}

export function SemesterPicker({ value, onChange, error }: SemesterPickerProps) {
  const { t, locale } = useTranslation()
  const options = upcomingSemesterCodes(4)

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
    </div>
  )
}
