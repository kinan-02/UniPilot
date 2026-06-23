import { useMemo } from 'react'
import { useTranslation } from '../../i18n'
import {
  buildTranscriptSemesterOptions,
  defaultSemesterCode,
  groupSemesterCodesByAcademicYear,
  semesterLabel,
} from '../../lib/semester'
import { cn } from '../../lib/utils'

type TranscriptSemesterPickerProps = {
  value: string
  onChange: (code: string) => void
  catalogYear?: number | null
  currentSemesterCode?: string | null
  existingSemesterCodes?: string[]
  error?: string
  disabled?: boolean
}

export function TranscriptSemesterPicker({
  value,
  onChange,
  catalogYear,
  currentSemesterCode,
  existingSemesterCodes = [],
  error,
  disabled,
}: TranscriptSemesterPickerProps) {
  const { t, locale } = useTranslation()

  const options = useMemo(
    () =>
      buildTranscriptSemesterOptions({
        catalogYear,
        currentSemesterCode,
        existingSemesterCodes,
      }),
    [catalogYear, currentSemesterCode, existingSemesterCodes],
  )

  const groupedOptions = useMemo(() => groupSemesterCodesByAcademicYear(options), [options])

  return (
    <div className="flex min-w-[220px] flex-col gap-2" data-testid="transcript-semester-picker">
      <label htmlFor="transcript-semester" className="text-sm font-medium text-[var(--color-text)]">
        {t('transcript.semesterTaken')}
      </label>
      <p className="text-xs text-[var(--color-text-muted)]">{t('transcript.semesterTakenHint')}</p>
      <select
        id="transcript-semester"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className={cn(
          'h-11 w-full rounded-xl border bg-white px-3 text-sm',
          'focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
          error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        {value && !options.includes(value) ? (
          <option value={value}>
            {semesterLabel(value, locale)} ({value})
          </option>
        ) : null}
        {groupedOptions.map((group) => (
          <optgroup
            key={group.academicYear}
            label={t('transcript.academicYearGroup').replace(
              '{years}',
              `${group.academicYear}-${group.academicYear + 1}`,
            )}
          >
            {group.semesters.map((code) => (
              <option key={code} value={code}>
                {semesterLabel(code, locale)} ({code})
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-3 py-2.5">
        <label
          htmlFor="transcript-semester-custom"
          className="text-xs font-medium text-[var(--color-text-muted)]"
        >
          {t('transcript.customSemester')}
        </label>
        <input
          id="transcript-semester-custom"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={defaultSemesterCode()}
          disabled={disabled}
          className={cn(
            'mt-1.5 h-9 w-full rounded-lg border bg-white px-2.5 font-mono text-xs',
            'focus:border-[var(--color-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary)]/15',
            error ? 'border-[var(--color-danger)]' : 'border-[var(--color-border)]',
          )}
          data-testid="transcript-semester-custom"
        />
        <p className="mt-1.5 text-[11px] text-[var(--color-text-muted)]">
          {t('transcript.customSemesterHint')}
        </p>
      </div>
      {error ? <p className="text-xs text-[var(--color-danger)]">{error}</p> : null}
    </div>
  )
}
