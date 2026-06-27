import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Award, BookOpen, Briefcase, ChevronDown, GraduationCap, Stethoscope } from 'lucide-react'
import { catalogApi, profileApi } from '../api/endpoints'
import { isAuthError, useAuth } from '../auth/AuthContext'
import { OnboardingShell } from '../components/onboarding/OnboardingShell'
import { PathOptionCard } from '../components/profile/PathOptionCard'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import {
  buildAcademicPathPayload,
  optionLabel,
  resolveDegreeIdFromPathOption,
} from '../lib/profilePrograms'
import { defaultSemesterCode, parseSemesterCode } from '../lib/semester'
import {
  hasStudentProfile,
  invalidateStudentProfile,
  useStudentProfileQuery,
} from '../lib/studentProfileQuery'
import { cn } from '../lib/utils'
import { validateSemesterCode } from '../lib/validation'
import type { CatalogFaculty } from '../types/api'

const PROGRAM_TYPES = [
  { id: 'BSc', icon: GraduationCap },
  { id: 'MSc', icon: BookOpen },
  { id: 'PhD', icon: Award },
  { id: 'MBA', icon: Briefcase },
  { id: 'MD', icon: Stethoscope },
] as const

const STEP_COUNT = 4

function facultyLabel(faculty: CatalogFaculty) {
  return faculty.nameHe ?? faculty.name ?? faculty.nameEn ?? faculty.facultyId
}

export function OnboardingPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user, isLoading: authLoading } = useAuth()
  const { t, locale } = useTranslation()
  const initialSemester = defaultSemesterCode()
  const initialYear = String(parseSemesterCode(initialSemester)?.academicYear ?? new Date().getFullYear())

  const [step, setStep] = useState(0)
  const [facultyId, setFacultyId] = useState('')
  const [programType, setProgramType] = useState('BSc')
  const [primaryOptionId, setPrimaryOptionId] = useState('')
  const [supplementalOptionIds, setSupplementalOptionIds] = useState<string[]>([])
  const [catalogYear, setCatalogYear] = useState(initialYear)
  const [semesterCode, setSemesterCode] = useState(initialSemester)
  const [showOptionalPaths, setShowOptionalPaths] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const profileQuery = useStudentProfileQuery()

  const facultiesQuery = useQuery({
    queryKey: ['academic-faculties', programType],
    queryFn: () => catalogApi.academicFaculties('technion', programType),
  })

  const pathOptionsQuery = useQuery({
    queryKey: ['path-options', facultyId, programType],
    queryFn: () =>
      catalogApi.pathOptions({
        facultyId: facultyId || undefined,
        programType,
      }),
    enabled: Boolean(facultyId),
  })

  useEffect(() => {
    if (profileQuery.isSuccess && hasStudentProfile(profileQuery.data)) {
      navigate('/', { replace: true })
    }
  }, [profileQuery.isSuccess, profileQuery.data, navigate])

  useEffect(() => {
    const faculties = facultiesQuery.data?.items ?? []
    if (faculties.length === 0) {
      if (facultyId) setFacultyId('')
      return
    }
    const stillValid = faculties.some((faculty) => faculty.facultyId === facultyId)
    if (!facultyId || !stillValid) {
      setFacultyId(faculties[0].facultyId)
    }
  }, [facultiesQuery.data, facultyId])

  useEffect(() => {
    setPrimaryOptionId('')
    setSupplementalOptionIds([])
    setShowOptionalPaths(false)
  }, [facultyId, programType])

  const pathOptions = (pathOptionsQuery.data?.items ?? []).filter((option) => Boolean(option.id))
  const primaryOptions = useMemo(() => {
    if (programType === 'MD') {
      return pathOptions.filter((option) => (option.studyLevels ?? []).includes('MD'))
    }
    return pathOptions.filter((option) => option.selectableAsPrimary)
  }, [pathOptions, programType])
  const supplementalOptions = useMemo(
    () => pathOptions.filter((option) => !option.selectableAsPrimary),
    [pathOptions],
  )
  const selectedPrimary = primaryOptions.find((option) => option.id === primaryOptionId)
  const selectedSupplemental = supplementalOptions.filter((option) =>
    supplementalOptionIds.includes(option.id ?? ''),
  )

  const stepLabels = [
    t('onboarding.steps.level'),
    t('onboarding.steps.faculty'),
    t('onboarding.steps.program'),
    t('onboarding.steps.semester'),
  ]

  const stepTitleKeys = ['level', 'faculty', 'program', 'semester'] as const
  const stepTitle = t(`onboarding.stepTitles.${stepTitleKeys[step]}`)
  const stepHint = t(`onboarding.stepHints.${stepTitleKeys[step]}`)

  const facultiesLoading = facultiesQuery.isLoading
  const pathOptionsLoading = pathOptionsQuery.isLoading && Boolean(facultyId)
  const optionsError = facultiesQuery.isError || pathOptionsQuery.isError
  const optionsEmpty =
    !pathOptionsLoading && !optionsError && Boolean(facultyId) && primaryOptions.length === 0

  const toggleSupplemental = (optionId: string) => {
    if (supplementalOptionIds.includes(optionId)) {
      setSupplementalOptionIds(supplementalOptionIds.filter((id) => id !== optionId))
      return
    }
    setSupplementalOptionIds([...supplementalOptionIds, optionId])
  }

  const validateCurrentStep = () => {
    setError('')
    if (step === 1 && !facultyId) {
      setError(t('profilePrograms.selectFaculty'))
      return false
    }
    if (step === 2) {
      if (optionsError) {
        setError(t('onboarding.programsLoadFailed'))
        return false
      }
      if (optionsEmpty) {
        setError(t('onboarding.programsEmpty'))
        return false
      }
      if (!primaryOptionId) {
        setError(t('onboarding.selectProgram'))
        return false
      }
    }
    if (step === 3) {
      const semesterResult = validateSemesterCode(semesterCode)
      if (!semesterResult.ok) {
        setError(t(semesterResult.message))
        return false
      }
    }
    return true
  }

  const goNext = () => {
    if (!validateCurrentStep()) return
    setStep((current) => Math.min(current + 1, STEP_COUNT - 1))
  }

  const goBack = () => {
    setError('')
    setStep((current) => Math.max(current - 1, 0))
  }

  const handleSubmit = async () => {
    if (!validateCurrentStep()) return

    const resolvedDegreeId = resolveDegreeIdFromPathOption(selectedPrimary)
    if (!resolvedDegreeId) {
      setError(t('onboarding.selectProgram'))
      setStep(2)
      return
    }

    setLoading(true)
    setError('')
    try {
      await profileApi.create({
        institutionId: 'technion',
        facultyId: facultyId || undefined,
        programType,
        degreeId: resolvedDegreeId,
        catalogYear: Number(catalogYear),
        currentSemesterCode: semesterCode,
        academicPath: buildAcademicPathPayload(selectedPrimary, selectedSupplemental),
      })
      await invalidateStudentProfile(queryClient)
      navigate('/', { replace: true })
    } catch (err) {
      if (isAuthError(err) && err.status === 409) {
        await invalidateStudentProfile(queryClient)
        navigate('/', { replace: true })
        return
      }
      setError(isAuthError(err) ? err.message : t('onboarding.saveFailed'))
    } finally {
      setLoading(false)
    }
  }

  if (authLoading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (!profileQuery.isFetched || profileQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  if (profileQuery.isSuccess && hasStudentProfile(profileQuery.data)) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  const stepContent = (() => {
    switch (step) {
      case 0:
        return (
          <div className="grid grid-cols-2 gap-3">
            {PROGRAM_TYPES.map(({ id, icon: Icon }) => (
              <button
                key={id}
                type="button"
                data-testid={`program-type-${id}`}
                className={cn(
                  'flex flex-col items-center gap-2 rounded-2xl border p-5 text-center transition-all',
                  programType === id
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5 shadow-[var(--shadow-card)]'
                    : 'border-[var(--color-border)] bg-white hover:border-[var(--color-primary)]/40',
                )}
                onClick={() => setProgramType(id)}
              >
                <span
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-xl',
                    programType === id
                      ? 'bg-[var(--color-primary)] text-white'
                      : 'bg-[var(--color-surface-muted)] text-[var(--color-text-muted)]',
                  )}
                >
                  <Icon className="h-5 w-5" aria-hidden />
                </span>
                <span className="text-sm font-semibold text-[var(--color-text)]">{id}</span>
              </button>
            ))}
          </div>
        )

      case 1:
        if (facultiesLoading) {
          return (
            <div className="flex justify-center py-8">
              <Spinner />
            </div>
          )
        }
        return (
          <div className="space-y-2">
            {(facultiesQuery.data?.items ?? []).map((faculty) => (
              <button
                key={faculty.id ?? faculty.facultyId}
                type="button"
                data-testid={`faculty-${faculty.facultyId}`}
                className={cn(
                  'w-full rounded-2xl border px-4 py-3.5 text-start text-sm font-medium transition-all',
                  facultyId === faculty.facultyId
                    ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5 text-[var(--color-text)]'
                    : 'border-[var(--color-border)] bg-white text-[var(--color-text)] hover:border-[var(--color-primary)]/40',
                )}
                onClick={() => setFacultyId(faculty.facultyId)}
              >
                {facultyLabel(faculty)}
              </button>
            ))}
          </div>
        )

      case 2:
        return (
          <div className="space-y-4">
            {pathOptionsLoading ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : null}
            {optionsError ? (
              <p className="text-sm text-[var(--color-danger)]">{t('onboarding.programsLoadFailed')}</p>
            ) : null}
            {!pathOptionsLoading && !optionsError && optionsEmpty ? (
              <p className="text-sm text-[var(--color-danger)]">{t('onboarding.programsEmpty')}</p>
            ) : null}
            {!pathOptionsLoading && primaryOptions.length > 0 ? (
              <div className="grid gap-3">
                {primaryOptions.map((option) => (
                  <PathOptionCard
                    key={option.id ?? option.optionKey}
                    option={option}
                    selected={primaryOptionId === option.id}
                    onSelect={() => setPrimaryOptionId(option.id ?? '')}
                    name="primary-program"
                  />
                ))}
              </div>
            ) : null}

            {supplementalOptions.length > 0 ? (
              <div className="pt-2">
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-xl border border-dashed border-[var(--color-border)] px-4 py-3 text-sm font-medium text-[var(--color-text-muted)] transition-colors hover:border-[var(--color-primary)]/40 hover:text-[var(--color-text)]"
                  onClick={() => setShowOptionalPaths((open) => !open)}
                  aria-expanded={showOptionalPaths}
                >
                  {t('onboarding.optionalPaths')}
                  <ChevronDown
                    className={cn('h-4 w-4 transition-transform', showOptionalPaths && 'rotate-180')}
                    aria-hidden
                  />
                </button>
                {showOptionalPaths ? (
                  <div className="mt-3 grid gap-3">
                    <p className="text-xs text-[var(--color-text-muted)]">{t('onboarding.optionalPathsHint')}</p>
                    {supplementalOptions.map((option) => (
                      <PathOptionCard
                        key={option.id ?? option.optionKey}
                        option={option}
                        selected={supplementalOptionIds.includes(option.id ?? '')}
                        onSelect={() => toggleSupplemental(option.id ?? '')}
                        mode="checkbox"
                      />
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        )

      case 3:
        return (
          <div className="space-y-5">
            {selectedPrimary ? (
              <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] px-4 py-3">
                <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t('profilePrograms.selectionSummary')}
                </p>
                <p className="mt-1 text-sm font-medium text-[var(--color-text)]">
                  {optionLabel(selectedPrimary, locale)}
                </p>
                {selectedSupplemental.length > 0 ? (
                  <ul className="mt-2 space-y-0.5 text-xs text-[var(--color-text-muted)]">
                    {selectedSupplemental.map((option) => (
                      <li key={option.id ?? option.optionKey}>+ {optionLabel(option, locale)}</li>
                    ))}
                  </ul>
                ) : null}
              </div>
            ) : null}

            <div className="grid gap-4 sm:grid-cols-2">
              <Input
                label={t('onboarding.catalogYear')}
                type="number"
                value={catalogYear}
                onChange={(e) => setCatalogYear(e.target.value)}
                required
              />
              <Input
                label={t('onboarding.currentSemester')}
                placeholder="2025-1"
                value={semesterCode}
                onChange={(e) => setSemesterCode(e.target.value)}
                required
              />
            </div>
            <p className="text-xs text-[var(--color-text-muted)]">{t('onboarding.semesterFormatHint')}</p>
          </div>
        )

      default:
        return null
    }
  })()

  const isLastStep = step === STEP_COUNT - 1
  const continueDisabled =
    loading ||
    (step === 1 && (facultiesLoading || !facultyId)) ||
    (step === 2 && (pathOptionsLoading || optionsError || optionsEmpty || !primaryOptionId))

  return (
    <OnboardingShell
      stepLabels={stepLabels}
      currentStep={step}
      stepTitle={stepTitle}
      stepHint={stepHint}
      loading={false}
      footer={
        <div className="space-y-3">
          {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
          <div className="flex gap-3">
            {step > 0 ? (
              <Button type="button" variant="secondary" onClick={goBack} disabled={loading}>
                {t('onboarding.back')}
              </Button>
            ) : null}
            {isLastStep ? (
              <Button
                type="button"
                className="flex-1"
                loading={loading}
                data-testid="onboarding-finish"
                onClick={() => void handleSubmit()}
              >
                {t('onboarding.continueDashboard')}
              </Button>
            ) : (
              <Button
                type="button"
                className="flex-1"
                data-testid="onboarding-continue"
                disabled={continueDisabled}
                onClick={goNext}
              >
                {t('onboarding.continue')}
              </Button>
            )}
          </div>
        </div>
      }
    >
      <div key={step} className="animate-fade-in">
        {stepContent}
      </div>
    </OnboardingShell>
  )
}
