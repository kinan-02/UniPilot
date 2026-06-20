import { useParams } from 'react-router-dom'
import { ManualPlanBuilder } from '../components/plans/ManualPlanBuilder'
import { PageHeader } from '../components/ui/Card'
import { useTranslation } from '../i18n'

export function PlanBuilderPage() {
  const { id } = useParams()
  const { t } = useTranslation()

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader title={id ? t('plans.editPlan') : t('plans.newPlan')} />
      <ManualPlanBuilder planId={id} />
    </div>
  )
}
