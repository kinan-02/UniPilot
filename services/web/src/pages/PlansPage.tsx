import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { plansApi } from '../api/endpoints'
import { Button } from '../components/ui/Button'
import { Badge, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { useTranslation } from '../i18n'
import { semesterLabel } from '../lib/semester'

export function PlansPage() {
  const { t, locale } = useTranslation()
  const navigate = useNavigate()

  const plansQuery = useQuery({
    queryKey: ['plans'],
    queryFn: plansApi.list,
  })

  const plans = plansQuery.data?.semesterPlans ?? []

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader title={t('plans.title')} description={t('plans.subtitle')} />

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
              plan.semesters?.reduce((sum, semester) => sum + (semester.plannedCourses?.length ?? 0), 0) ?? 0
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
    </div>
  )
}
