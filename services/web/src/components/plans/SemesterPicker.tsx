import { useTranslation } from '../../i18n'
import { defaultSemesterCode, semesterLabel, upcomingSemesterCodes } from '../../lib/semester'
import { cn } from '../../lib/utils'

type SemesterPickerProps = {
  value: string
  onChange: (code: string) => void
  error?: string
  disabled?: boolean
}

export function SemesterPicker({ value, onChange, error, disabled }: SemesterPickerProps) {
  const { t, locale } = useTranslation()
  const options = upcomingSemesterCodes(8)
  const selectOptions = options.includes(value) ? options : [value, ...options]

  return (
    <div className="flex min-w-[220px] flex-col gap-1">
      <label htmlFor="planner-semester" className="text-xs font-medium text-[var(--color-text-muted)]">
        {t('common.semester')}
      </label>
      <select
        id="planner-semester"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={cn(
          'h-9 w-full rounded-xl border bg-white px-3 text-sm',
          'focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
          error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        {selectOptions.map((code) => (
          <option key={code} value={code}>
            {semesterLabel(code, locale)} ({code})
          </option>
        ))}
      </select>
      <details className="text-xs">
        <summary className="cursor-pointer text-[var(--color-text-muted)] hover:text-[var(--color-primary)] [&::-webkit-details-marker]:hidden">
          {t('plans.customSemesterCode')}
        </summary>
        <input
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={defaultSemesterCode()}
          disabled={disabled}
          className={cn(
            'mt-1.5 h-8 w-full rounded-lg border bg-white px-2 font-mono text-xs',
            'focus:border-[var(--color-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]/15',
            error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
          )}
        />
      </details>
      {error ? <p className="text-xs text-[var(--color-danger)]">{error}</p> : null}
    </div>
  )
}
