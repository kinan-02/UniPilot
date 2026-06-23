import { useMemo } from 'react'
import type { CatalogFaculty, CatalogPathOption } from '../../types/api'
import { optionLabel } from '../../lib/profilePrograms'
import { PathOptionCard } from './PathOptionCard'
import { Select } from '../ui/Input'
import { cn } from '../../lib/utils'

const PROGRAM_TYPES = ['BSc', 'MSc', 'PhD', 'MBA'] as const

type ProfileProgramFieldsProps = {
  faculties: CatalogFaculty[]
  facultiesLoading: boolean
  facultyId: string
  onFacultyIdChange: (value: string) => void
  programType: string
  onProgramTypeChange: (value: string) => void
  primaryOptions: CatalogPathOption[]
  primaryOptionId: string
  onPrimaryOptionIdChange: (value: string) => void
  supplementalOptions: CatalogPathOption[]
  supplementalOptionIds: string[]
  onSupplementalOptionIdsChange: (values: string[]) => void
  pathOptionsLoading: boolean
  optionsError: boolean
  t: (key: string) => string
}

export function ProfileProgramFields({
  faculties,
  facultiesLoading,
  facultyId,
  onFacultyIdChange,
  programType,
  onProgramTypeChange,
  primaryOptions,
  primaryOptionId,
  onPrimaryOptionIdChange,
  supplementalOptions,
  supplementalOptionIds,
  onSupplementalOptionIdsChange,
  pathOptionsLoading,
  optionsError,
  t,
}: ProfileProgramFieldsProps) {
  const groupedSupplemental = useMemo(() => {
    const groups: Record<string, CatalogPathOption[]> = {}
    for (const option of supplementalOptions) {
      const key = option.kind
      groups[key] = groups[key] ?? []
      groups[key].push(option)
    }
    return groups
  }, [supplementalOptions])

  const supplementalLabel = (kind: string) => {
    switch (kind) {
      case 'special_program':
        return t('profilePrograms.specialPrograms')
      case 'minor':
        return t('profilePrograms.minors')
      case 'dne_specialization':
        return t('profilePrograms.specializations')
      case 'graduate_program':
        return t('profilePrograms.graduatePrograms')
      default:
        return kind
    }
  }

  const selectedPrimary = primaryOptions.find((option) => option.id === primaryOptionId)
  const selectedSupplemental = supplementalOptions.filter((option) =>
    supplementalOptionIds.includes(option.id ?? ''),
  )

  const wizardProgress = [
    Boolean(programType),
    Boolean(facultyId),
    Boolean(primaryOptionId),
  ]
  const completedSteps = wizardProgress.filter(Boolean).length

  const toggleSupplemental = (optionId: string) => {
    if (supplementalOptionIds.includes(optionId)) {
      onSupplementalOptionIdsChange(supplementalOptionIds.filter((id) => id !== optionId))
      return
    }
    onSupplementalOptionIdsChange([...supplementalOptionIds, optionId])
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2" aria-label={t('profilePrograms.wizardTitle')}>
        <div className="flex gap-2">
          {wizardProgress.map((done, index) => (
            <div
              key={index}
              className={cn(
                'h-1.5 flex-1 rounded-full transition-colors',
                done ? 'bg-[var(--color-primary)]' : 'bg-[var(--color-border)]',
              )}
            />
          ))}
        </div>
        <p className="text-xs text-[var(--color-text-muted)]">
          {t('profilePrograms.wizardProgress').replace('{current}', String(completedSteps)).replace('{total}', '3')}
        </p>
      </div>

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text)]">
            {t('profilePrograms.stepProgramType')}
          </h3>
          <p className="text-xs text-[var(--color-text-muted)]">{t('profilePrograms.stepProgramTypeHint')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {PROGRAM_TYPES.map((type) => (
            <button
              key={type}
              type="button"
              className={cn(
                'rounded-full border px-4 py-2 text-sm font-medium transition-colors',
                programType === type
                  ? 'border-[var(--color-primary)] bg-[var(--color-primary)] text-white'
                  : 'border-[var(--color-border)] bg-white text-[var(--color-text)] hover:border-[var(--color-primary)]/40',
              )}
              onClick={() => onProgramTypeChange(type)}
            >
              {type}
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text)]">
            {t('profilePrograms.stepFaculty')}
          </h3>
          <p className="text-xs text-[var(--color-text-muted)]">{t('profilePrograms.stepFacultyHint')}</p>
        </div>
        <Select
          id="faculty"
          label={t('profilePrograms.faculty')}
          value={facultyId}
          onChange={(event) => onFacultyIdChange(event.target.value)}
          disabled={facultiesLoading || faculties.length === 0}
        >
          <option value="">{t('profilePrograms.selectFaculty')}</option>
          {faculties.map((faculty) => (
            <option key={faculty.id ?? faculty.facultyId} value={faculty.facultyId}>
              {faculty.nameHe ?? faculty.name ?? faculty.nameEn ?? faculty.facultyId}
            </option>
          ))}
        </Select>
      </section>

      <section className="space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-[var(--color-text)]">
            {t('onboarding.degreeProgram')}
          </h3>
          <p className="text-xs text-[var(--color-text-muted)]">{t('profilePrograms.stepPrimaryHint')}</p>
        </div>

        {pathOptionsLoading ? (
          <p className="text-sm text-[var(--color-muted)]">{t('onboarding.programsLoading')}</p>
        ) : null}
        {optionsError ? (
          <p className="text-sm text-[var(--color-danger)]">{t('onboarding.programsLoadFailed')}</p>
        ) : null}
        {!pathOptionsLoading && !optionsError && facultyId && primaryOptions.length === 0 ? (
          <p className="text-sm text-[var(--color-danger)]">{t('onboarding.programsEmpty')}</p>
        ) : null}

        {!pathOptionsLoading && primaryOptions.length > 0 ? (
          <div className="grid gap-3">
            {primaryOptions.map((option) => (
              <PathOptionCard
                key={option.id ?? option.optionKey}
                option={option}
                selected={primaryOptionId === option.id}
                onSelect={() => onPrimaryOptionIdChange(option.id ?? '')}
                name="primary-program"
              />
            ))}
          </div>
        ) : null}
      </section>

      {Object.entries(groupedSupplemental).map(([kind, options]) => (
        <section key={kind} className="space-y-3">
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-text)]">{supplementalLabel(kind)}</h3>
            <p className="text-xs text-[var(--color-text-muted)]">{t('profilePrograms.supplementalHint')}</p>
          </div>
          <div className="grid gap-3">
            {options.map((option) => (
              <PathOptionCard
                key={option.id ?? option.optionKey}
                option={option}
                selected={supplementalOptionIds.includes(option.id ?? '')}
                onSelect={() => toggleSupplemental(option.id ?? '')}
                mode="checkbox"
              />
            ))}
          </div>
        </section>
      ))}

      {selectedPrimary || selectedSupplemental.length > 0 ? (
        <section className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
          <h3 className="text-sm font-semibold text-[var(--color-text)]">
            {t('profilePrograms.selectionSummary')}
          </h3>
          <ul className="mt-2 space-y-1 text-sm text-[var(--color-text-muted)]">
            {selectedPrimary ? <li>{optionLabel(selectedPrimary)}</li> : null}
            {selectedSupplemental.map((option) => (
              <li key={option.id ?? option.optionKey}>+ {optionLabel(option)}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  )
}
