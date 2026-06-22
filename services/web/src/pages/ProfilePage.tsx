import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { catalogApi, profileApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { AcademicPathFields } from '../components/profile/AcademicPathFields'
import { Button } from '../components/ui/Button'
import { Card, PageHeader, Spinner } from '../components/ui/Card'
import { Input, Select } from '../components/ui/Input'
import { buildAcademicPathForProgram, trackSlugFromProgram } from '../lib/academicPath'
import { useTranslation } from '../i18n'

export function ProfilePage() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const [programType, setProgramType] = useState('BSc')
  const [degreeId, setDegreeId] = useState('')
  const [catalogYear, setCatalogYear] = useState('2025')
  const [semesterCode, setSemesterCode] = useState('2025-1')
  const [maxCredits, setMaxCredits] = useState('18')
  const [trackSlug, setTrackSlug] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')

  const profileQuery = useQuery({
    queryKey: ['profile'],
    queryFn: profileApi.get,
    retry: false,
  })

  const programsQuery = useQuery({
    queryKey: ['degree-programs'],
    queryFn: catalogApi.degreePrograms,
  })

  useEffect(() => {
    const profile = profileQuery.data?.profile
    if (!profile) return
    setProgramType(profile.programType)
    setDegreeId(profile.degreeId ?? '')
    setCatalogYear(String(profile.catalogYear))
    setSemesterCode(profile.currentSemesterCode)
    setMaxCredits(String(profile.preferences?.maxCreditsPerSemester ?? 18))
    setTrackSlug(profile.academicPath?.trackSlug ?? '')
  }, [profileQuery.data])

  const programs = (programsQuery.data?.items ?? []).filter((program) => Boolean(program.id))
  const selectedProgram = programs.find((program) => program.id === degreeId)

  useEffect(() => {
    if (trackSlug) return
    const suggested = trackSlugFromProgram(selectedProgram)
    if (suggested) setTrackSlug(suggested)
  }, [selectedProgram?.id, trackSlug])

  const saveMutation = useMutation({
    mutationFn: () => {
      const academicPath = buildAcademicPathForProgram(selectedProgram, {
        trackSlug,
        minors: profileQuery.data?.profile?.academicPath?.minors,
        specialPrograms: profileQuery.data?.profile?.academicPath?.specialPrograms,
        graduatePrograms: profileQuery.data?.profile?.academicPath?.graduatePrograms,
        specializations: profileQuery.data?.profile?.academicPath?.specializations,
      })
      const body = {
        programType,
        degreeId: degreeId || undefined,
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
      queryClient.invalidateQueries({ queryKey: ['curriculum-graph'] })
      setMessage('Profile saved')
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

  const programsLoading = programsQuery.isLoading
  const programsLoadError = programsQuery.isError
  const programsEmpty = !programsLoading && !programsLoadError && programs.length === 0

  return (
    <div className="animate-fade-in">
      <PageHeader
        title="Student profile"
        description="Your program context drives catalog filtering, progress calculation, and semester planning."
      />
      <Card className="max-w-xl">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            saveMutation.mutate()
          }}
        >
          <Select label="Program type" value={programType} onChange={(e) => setProgramType(e.target.value)}>
            <option value="BSc">BSc</option>
            <option value="MSc">MSc</option>
          </Select>
          <Select
            label="Degree program"
            value={degreeId}
            onChange={(e) => setDegreeId(e.target.value)}
            disabled={programsLoading || programsEmpty || programsLoadError}
          >
            <option value="">None selected</option>
            {programs.map((p) => (
              <option key={p.id} value={p.id!}>
                {p.name ?? p.nameEn ?? p.programCode}
              </option>
            ))}
          </Select>
          {programsLoading ? <p className="text-sm text-[var(--color-muted)]">Loading degree programs…</p> : null}
          {programsLoadError ? (
            <p className="text-sm text-[var(--color-danger)]">Could not load degree programs</p>
          ) : null}
          {programsEmpty ? (
            <p className="text-sm text-[var(--color-danger)]">No degree programs are available yet.</p>
          ) : null}
          <AcademicPathFields
            programs={programs}
            degreeId={degreeId}
            trackSlug={trackSlug}
            onTrackSlugChange={setTrackSlug}
            t={t}
          />
          <Input
            label="Catalog year"
            type="number"
            value={catalogYear}
            onChange={(e) => setCatalogYear(e.target.value)}
          />
          <Input
            label="Current semester"
            value={semesterCode}
            onChange={(e) => setSemesterCode(e.target.value)}
          />
          <Input
            label="Max credits per semester"
            type="number"
            min={1}
            max={36}
            value={maxCredits}
            onChange={(e) => setMaxCredits(e.target.value)}
          />
          {message ? <p className="text-sm text-[var(--color-success)]">{message}</p> : null}
          {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
          <Button type="submit" loading={saveMutation.isPending}>
            Save profile
          </Button>
        </form>
      </Card>
    </div>
  )
}
