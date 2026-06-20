import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { catalogApi, profileApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Input, Select } from '../components/ui/Input'
import { PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { validateSemesterCode } from '../lib/validation'

export function OnboardingPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { t } = useTranslation()
  const [programType, setProgramType] = useState('BSc')
  const [degreeId, setDegreeId] = useState('')
  const [catalogYear, setCatalogYear] = useState('2025')
  const [semesterCode, setSemesterCode] = useState('2025-1')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const profileQuery = useQuery({
    queryKey: ['profile'],
    queryFn: async () => {
      try {
        return await profileApi.get()
      } catch (err) {
        if (isAuthError(err) && err.status === 404) return null
        throw err
      }
    },
  })

  const programsQuery = useQuery({
    queryKey: ['degree-programs'],
    queryFn: catalogApi.degreePrograms,
  })

  useEffect(() => {
    if (profileQuery.data?.profile) {
      navigate('/', { replace: true })
    }
  }, [profileQuery.data, navigate])

  const programs = programsQuery.data?.items ?? []

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')

    const semesterResult = validateSemesterCode(semesterCode)
    if (!semesterResult.ok) {
      setError(t(semesterResult.message))
      return
    }
    if (!degreeId) {
      setError(t('onboarding.selectProgram'))
      return
    }

    setLoading(true)
    try {
      await profileApi.create({
        institutionId: 'technion',
        programType,
        degreeId: degreeId || undefined,
        catalogYear: Number(catalogYear),
        currentSemesterCode: semesterCode,
      })
      await queryClient.invalidateQueries({ queryKey: ['profile'] })
      navigate('/')
    } catch (err) {
      setError(isAuthError(err) ? err.message : t('onboarding.saveFailed'))
    } finally {
      setLoading(false)
    }
  }

  if (profileQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-xl px-4 py-12 animate-fade-in">
      <PageHeader title={t('onboarding.title')} description={t('onboarding.subtitle')} />
      <Card>
        <form className="space-y-4" onSubmit={handleSubmit}>
          <Select
            id="program-type"
            label={t('onboarding.programType')} value={programType} onChange={(e) => setProgramType(e.target.value)}>
            <option value="BSc">BSc</option>
            <option value="MSc">MSc</option>
          </Select>
          <Select
            id="degree-program"
            label={t('onboarding.degreeProgram')}
            value={degreeId}
            onChange={(e) => setDegreeId(e.target.value)}
            required
          >
            <option value="">{t('onboarding.selectProgram')}</option>
            {programs.map((program) => (
              <option key={program.programCode} value={program.id ?? ''}>
                {program.name ?? program.nameHebrew ?? program.programCode}
              </option>
            ))}
          </Select>
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
          {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
          <Button type="submit" className="w-full" loading={loading}>
            {t('onboarding.continueDashboard')}
          </Button>
        </form>
      </Card>
    </div>
  )
}
