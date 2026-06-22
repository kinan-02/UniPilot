import { useMemo } from 'react'
import type { DegreeProgram } from '../../types/api'
import { trackSlugFromProgram } from '../../lib/academicPath'

type AcademicPathFieldsProps = {
  programs: DegreeProgram[]
  degreeId: string
  trackSlug: string
  onTrackSlugChange: (slug: string) => void
  t: (key: string) => string
}

export function AcademicPathFields({
  programs,
  degreeId,
  trackSlug,
  onTrackSlugChange,
  t,
}: AcademicPathFieldsProps) {
  const selectedProgram = useMemo(
    () => programs.find((program) => program.id === degreeId),
    [programs, degreeId],
  )

  const resolvedSlug = trackSlugFromProgram(selectedProgram)
  const displaySlug = trackSlug || resolvedSlug || ''

  if (!degreeId || !resolvedSlug) {
    return (
      <p className="text-sm text-[var(--color-text-muted)]">{t('academicPath.selectDegreeFirst')}</p>
    )
  }

  return (
    <div className="space-y-2">
      <label className="text-sm font-medium" htmlFor="academic-track">
        {t('academicPath.trackLabel')}
      </label>
      <input
        id="academic-track"
        className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-3 py-2 text-sm"
        value={displaySlug}
        readOnly
        aria-readonly="true"
      />
      <p className="text-xs text-[var(--color-text-muted)]">{t('academicPath.trackHint')}</p>
      {displaySlug !== trackSlug ? (
        <button
          type="button"
          className="text-xs font-medium text-[var(--color-primary)]"
          onClick={() => onTrackSlugChange(resolvedSlug)}
        >
          {t('academicPath.applySuggestedTrack')}
        </button>
      ) : null}
    </div>
  )
}
