import { useTranslation } from '../../i18n'
import { semesterLabel } from '../../lib/semester'
import { cn } from '../../lib/utils'

type SemesterPickerProps = {
  value: string
  onChange: (code: string) => void
  options: string[]
  loading?: boolean
  error?: string
  disabled?: boolean
}

export function SemesterPicker({
  value,
  onChange,
  options,
  loading,
  error,
  disabled,
}: SemesterPickerProps) {
  const { t, locale } = useTranslation()
  const selectOptions = options.includes(value) ? options : value ? [value, ...options] : options

  return (
    <div className="flex min-w-[220px] flex-col gap-1">
      <label htmlFor="planner-semester" className="text-xs font-medium text-[var(--color-text-muted)]">
        {t('common.semester')}
      </label>
      <select
        id="planner-semester"
        data-testid="planner-semester"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled || loading || selectOptions.length === 0}
        className={cn(
          'h-9 w-full rounded-xl border bg-white px-3 text-sm',
          'focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
          error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
          (disabled || loading) && 'cursor-not-allowed opacity-60',
        )}
      >
        {loading ? (
          <option value={value}>{t('common.loading')}</option>
        ) : selectOptions.length === 0 ? (
          <option value="">{t('plans.noPlannerSemesters')}</option>
        ) : (
          selectOptions.map((code) => (
            <option key={code} value={code}>
              {semesterLabel(code, locale)} ({code})
            </option>
          ))
        )}
      </select>
      {error ? <p className="text-xs text-[var(--color-danger)]">{error}</p> : null}
    </div>
  )
}
