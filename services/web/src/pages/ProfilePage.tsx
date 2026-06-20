import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { catalogApi, profileApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Card, PageHeader, Spinner } from '../components/ui/Card'
import { Input, Select } from '../components/ui/Input'

export function ProfilePage() {
  const queryClient = useQueryClient()
  const [programType, setProgramType] = useState('BSc')
  const [degreeId, setDegreeId] = useState('')
  const [catalogYear, setCatalogYear] = useState('2025')
  const [semesterCode, setSemesterCode] = useState('2025-1')
  const [maxCredits, setMaxCredits] = useState('18')
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
  }, [profileQuery.data])

  const saveMutation = useMutation({
    mutationFn: () =>
      profileQuery.data?.profile
        ? profileApi.update({
            programType,
            degreeId: degreeId || undefined,
            catalogYear: Number(catalogYear),
            currentSemesterCode: semesterCode,
            preferences: { maxCreditsPerSemester: Number(maxCredits) },
          })
        : profileApi.create({
            institutionId: 'technion',
            programType,
            degreeId: degreeId || undefined,
            catalogYear: Number(catalogYear),
            currentSemesterCode: semesterCode,
            preferences: { maxCreditsPerSemester: Number(maxCredits) },
          }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
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

  const programs = programsQuery.data?.items ?? []

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
          <Select label="Degree program" value={degreeId} onChange={(e) => setDegreeId(e.target.value)}>
            <option value="">None selected</option>
            {programs.map((p) => (
              <option key={p.programCode} value={p.id ?? ''}>
                {p.name ?? p.nameEn ?? p.programCode}
              </option>
            ))}
          </Select>
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
