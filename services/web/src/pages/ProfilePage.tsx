import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { catalogApi, profileApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { ProfileProgramFields } from '../components/profile/ProfileProgramFields'
import { Button } from '../components/ui/Button'
import { Card, PageHeader, Spinner } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { useTranslation } from '../i18n'
import {
  buildAcademicPathPayload,
  findPrimaryOptionId,
  resolveDegreeIdFromPathOption,
  resolveFacultyIdFromProfile,
  supplementalOptionIdsFromPath,
} from '../lib/profilePrograms'
import {
  invalidateStudentProfile,
  useStudentProfileQuery,
} from '../lib/studentProfileQuery'

export function ProfilePage() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const hydratedProfileIdRef = useRef<string | null>(null)
  const [facultyId, setFacultyId] = useState('')
  const [programType, setProgramType] = useState('BSc')
  const [primaryOptionId, setPrimaryOptionId] = useState('')
  const [supplementalOptionIds, setSupplementalOptionIds] = useState<string[]>([])
  const [catalogYear, setCatalogYear] = useState('2025')
  const [semesterCode, setSemesterCode] = useState('2025-1')
  const [maxCredits, setMaxCredits] = useState('18')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

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

  const pathOptions = (pathOptionsQuery.data?.items ?? []).filter((option) => Boolean(option.id))
  const primaryOptions = useMemo(
    () => pathOptions.filter((option) => option.selectableAsPrimary),
    [pathOptions],
  )
  const supplementalOptions = useMemo(
    () => pathOptions.filter((option) => !option.selectableAsPrimary),
    [pathOptions],
  )
  const selectedPrimary = primaryOptions.find((option) => option.id === primaryOptionId)
  const selectedSupplemental = supplementalOptions.filter((option) =>
    supplementalOptionIds.includes(option.id ?? ''),
  )

  useEffect(() => {
    const faculties = facultiesQuery.data?.items ?? []
    if (faculties.length === 0) {
      if (facultyId) setFacultyId('')
      return
    }
    const stillValid = faculties.some((faculty) => faculty.facultyId === facultyId)
    if (!facultyId || !stillValid) {
      const profile = profileQuery.data?.profile
      const preferred = resolveFacultyIdFromProfile(profile?.facultyId, pathOptions, faculties)
      setFacultyId(preferred || faculties[0].facultyId)
    }
  }, [facultiesQuery.data, facultyId, pathOptions, profileQuery.data])

  useEffect(() => {
    setPrimaryOptionId('')
    setSupplementalOptionIds([])
  }, [facultyId, programType])

  useEffect(() => {
    const profile = profileQuery.data?.profile
    if (!profile || pathOptions.length === 0) return
    if (hydratedProfileIdRef.current === profile.id) return

    setProgramType(profile.programType)
    setCatalogYear(String(profile.catalogYear))
    setSemesterCode(profile.currentSemesterCode)
    setMaxCredits(String(profile.preferences?.maxCreditsPerSemester ?? 18))
    setPrimaryOptionId(findPrimaryOptionId(profile.degreeId, pathOptions))
    setSupplementalOptionIds(supplementalOptionIdsFromPath(profile.academicPath, pathOptions))
    if (profile.facultyId) setFacultyId(profile.facultyId)
    hydratedProfileIdRef.current = profile.id
  }, [profileQuery.data, pathOptions])

  const saveMutation = useMutation({
    mutationFn: () => {
      const resolvedDegreeId = resolveDegreeIdFromPathOption(selectedPrimary)
      const academicPath = buildAcademicPathPayload(
        selectedPrimary,
        selectedSupplemental,
        profileQuery.data?.profile?.academicPath,
      )
      const body = {
        facultyId: facultyId || undefined,
        programType,
        degreeId: resolvedDegreeId || undefined,
        catalogYear: Number(catalogYear),
        currentSemesterCode: semesterCode,
        preferences: { maxCreditsPerSemester: Number(maxCredits) },
        ...(academicPath ? { academicPath } : {}),
      }
      return profileQuery.data?.profile
        ? profileApi.update(body)
        : profileApi.create({
            institutionId: 'technion',
            ...body,
          })
    },
    onSuccess: async () => {
      await invalidateStudentProfile(queryClient)
      queryClient.invalidateQueries({ queryKey: ['progress'] })
      queryClient.invalidateQueries({ queryKey: ['curriculum-graph'] })
      setMessage(t('profilePrograms.saveSuccess'))
      setError('')
    },
    onError: (err) => {
      setMessage('')
      setError(isAuthError(err) ? err.message : 'Could not save profile')
    },
  })

  if (profileQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  const facultiesLoading = facultiesQuery.isLoading
  const pathOptionsLoading = pathOptionsQuery.isLoading && Boolean(facultyId)
  const optionsError = facultiesQuery.isError || pathOptionsQuery.isError
  const optionsEmpty =
    !facultiesLoading &&
    !pathOptionsLoading &&
    !optionsError &&
    Boolean(facultyId) &&
    primaryOptions.length === 0

  return (
    <div className="animate-fade-in">
      <PageHeader
        title={t('onboarding.title')}
        description={t('profilePrograms.wizardSubtitle')}
      />
      <Card className="max-w-3xl overflow-hidden">
        <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)] px-6 py-4">
          <p className="text-sm font-medium text-[var(--color-text)]">{t('profilePrograms.wizardTitle')}</p>
        </div>
        <form
          className="space-y-6 p-6"
          onSubmit={(e) => {
            e.preventDefault()
            saveMutation.mutate()
          }}
        >
          <ProfileProgramFields
            faculties={facultiesQuery.data?.items ?? []}
            facultiesLoading={facultiesLoading}
            facultyId={facultyId}
            onFacultyIdChange={setFacultyId}
            programType={programType}
            onProgramTypeChange={setProgramType}
            primaryOptions={primaryOptions}
            primaryOptionId={primaryOptionId}
            onPrimaryOptionIdChange={setPrimaryOptionId}
            supplementalOptions={supplementalOptions}
            supplementalOptionIds={supplementalOptionIds}
            onSupplementalOptionIdsChange={setSupplementalOptionIds}
            pathOptionsLoading={pathOptionsLoading}
            optionsError={optionsError}
            t={t}
          />
          {optionsEmpty ? (
            <p className="text-sm text-[var(--color-danger)]">{t('onboarding.programsEmpty')}</p>
          ) : null}
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-muted)] p-4">
            <h3 className="text-sm font-semibold text-[var(--color-text)]">
              {t('profilePrograms.stepSemester')}
            </h3>
            <div className="mt-3 grid gap-4 sm:grid-cols-2">
              <Input
                label={t('onboarding.catalogYear')}
                type="number"
                value={catalogYear}
                onChange={(e) => setCatalogYear(e.target.value)}
              />
              <Input
                label={t('onboarding.currentSemester')}
                value={semesterCode}
                onChange={(e) => setSemesterCode(e.target.value)}
              />
            </div>
            <div className="mt-4">
              <Input
                label={t('profilePrograms.maxCredits')}
                type="number"
                min={1}
                max={36}
                value={maxCredits}
                onChange={(e) => setMaxCredits(e.target.value)}
              />
            </div>
          </div>
          {message ? <p className="text-sm text-[var(--color-success)]">{message}</p> : null}
          {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
          <Button
            type="submit"
            loading={saveMutation.isPending}
            disabled={facultiesLoading || pathOptionsLoading || optionsError}
          >
            {t('profilePrograms.save')}
          </Button>
        </form>
      </Card>
    </div>
  )
}
