import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { plansApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { Button } from '../components/ui/Button'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { useTranslation } from '../i18n'
import { defaultSemesterCode, semesterLabel } from '../lib/semester'
import { validateCredits, validateSemesterCode } from '../lib/validation'

type PlansTab = 'list' | 'generate'

export function PlansPage() {
  const { t, locale } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [tab, setTab] = useState<PlansTab>('list')
  const [semesterCode, setSemesterCode] = useState(defaultSemesterCode())
  const [maxCredits, setMaxCredits] = useState('12')
  const [generateError, setGenerateError] = useState('')

  const plansQuery = useQuery({
    queryKey: ['plans'],
    queryFn: plansApi.list,
  })

  const generateMutation = useMutation({
    mutationFn: () => {
      const semesterResult = validateSemesterCode(semesterCode)
      if (!semesterResult.ok) throw new Error(t(semesterResult.message))
      const creditsResult = validateCredits(Number(maxCredits))
      if (!creditsResult.ok) throw new Error(t(creditsResult.message))
      return plansApi.generate({
        semesterCode,
        maxCredits: Number(maxCredits),
      })
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['plans'] })
      setGenerateError('')
      navigate(`/plans/${data.semesterPlan.id}`)
    },
    onError: (err) => {
      setGenerateError(isAuthError(err) ? err.message : t('common.errorGeneric'))
    },
  })

  const plans = plansQuery.data?.semesterPlans ?? []

  const tabs: { id: PlansTab; label: string }[] = [
    { id: 'list', label: t('plans.myPlans') },
    { id: 'generate', label: t('plans.autoGenerate') },
  ]

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader title={t('plans.title')} description={t('plans.subtitle')} />

      <div className="flex flex-wrap gap-2 rounded-xl bg-[var(--color-surface-muted)] p-1">
        {tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition ${
              tab === item.id
                ? 'bg-white text-[var(--color-primary)] shadow-sm'
                : 'text-[var(--color-text-muted)] hover:text-[var(--color-text)]'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'list' ? (
        <>
          <div className="flex justify-end">
            <Button onClick={() => navigate('/plans/new')}>
              <Plus className="h-4 w-4" />
              {t('plans.newPlan')}
            </Button>
          </div>

          {plansQuery.isLoading ? (
            <div className="flex justify-center py-16">
              <Spinner />
            </div>
          ) : plans.length ? (
            <div className="grid gap-4">
              {plans.map((plan) => {
                const courseCount =
                  plan.semesters?.reduce((sum, s) => sum + (s.plannedCourses?.length ?? 0), 0) ?? 0
                const semester = plan.semesters?.[0]?.semesterCode
                return (
                  <div
                    key={plan.id}
                    className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-soft)]"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="font-medium">{plan.name ?? `Plan v${plan.version}`}</p>
                        <p className="text-sm text-[var(--color-text-muted)]">
                          {semester ? semesterLabel(semester, locale) : '—'} · {courseCount}{' '}
                          {t('plans.coursesCount')} ·{' '}
                          {plan.plannerType === 'manual'
                            ? t('plans.plannerManual')
                            : t('plans.plannerAuto')}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone="primary">v{plan.version}</Badge>
                        <Badge tone={plan.status === 'archived' ? 'neutral' : 'success'}>
                          {plan.status === 'draft'
                            ? t('plans.statusDraft')
                            : plan.status === 'archived'
                              ? t('plans.statusArchived')
                              : t('plans.statusActive')}
                        </Badge>
                        <Link to={`/plans/${plan.id}`}>
                          <Button variant="secondary" size="sm">
                            {t('plans.viewPlan')}
                          </Button>
                        </Link>
                        {plan.plannerType === 'manual' && plan.status !== 'archived' ? (
                          <Link to={`/plans/${plan.id}/edit`}>
                            <Button variant="ghost" size="sm">
                              {t('common.edit')}
                            </Button>
                          </Link>
                        ) : null}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <EmptyState title={t('plans.noPlans')} description={t('plans.noPlansHint')} />
          )}
        </>
      ) : null}

      {tab === 'generate' ? (
        <Card>
          <h2 className="mb-4 flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="h-4 w-4 text-[var(--color-primary)]" />
            {t('plans.autoGenerate')}
          </h2>
          <form
            className="flex flex-col gap-4 sm:flex-row sm:items-end"
            onSubmit={(e) => {
              e.preventDefault()
              generateMutation.mutate()
            }}
          >
            <Input
              label={t('plans.semesterCode')}
              value={semesterCode}
              onChange={(e) => setSemesterCode(e.target.value)}
              className="sm:max-w-[180px]"
            />
            <Input
              label={t('plans.maxCredits')}
              type="number"
              step="0.5"
              value={maxCredits}
              onChange={(e) => setMaxCredits(e.target.value)}
              className="sm:max-w-[180px]"
            />
            <Button type="submit" loading={generateMutation.isPending}>
              {t('plans.generate')}
            </Button>
          </form>
          {generateError ? (
            <p className="mt-3 text-sm text-[var(--color-danger)]">{generateError}</p>
          ) : null}
          {generateMutation.isSuccess ? (
            <p className="mt-3 text-sm text-[var(--color-success)]">
              {generateMutation.data?.semesterPlan.explanation?.summary ?? t('plans.savePlan')}
            </p>
          ) : null}
        </Card>
      ) : null}
    </div>
  )
}
