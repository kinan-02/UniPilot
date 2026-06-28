import { Link } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { CalendarDays, ClipboardList, ShieldAlert } from 'lucide-react'
import { Card } from '../ui/Card'

type DashboardStat = {
  label: string
  value: string
  hint: string
  icon: LucideIcon
  to?: string
  linkLabel?: string
}

type DashboardStatsRowProps = {
  semesterCode: string | undefined
  planCount: number
  riskCount: number
  t: (key: string) => string
}

function StatCard({ label, value, hint, icon: Icon, to, linkLabel }: DashboardStat) {
  const content = (
    <>
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-[var(--color-primary)]" aria-hidden />
        <p className="text-xs font-medium text-[var(--color-text-muted)]">{label}</p>
      </div>
      <p className="mt-3 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
      <p className="mt-1 text-xs text-[var(--color-text-muted)]">{hint}</p>
      {to && linkLabel ? (
        <span className="mt-3 inline-block text-xs font-medium text-[var(--color-primary)]">
          {linkLabel}
        </span>
      ) : null}
    </>
  )

  if (to) {
    return (
      <Link
        to={to}
        className="block rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white p-4 shadow-[var(--shadow-soft)] transition hover:border-[var(--color-primary)]/25 hover:shadow-[var(--shadow-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30"
        data-testid={`dashboard-stat-${to.replace('/', '') || 'home'}`}
      >
        {content}
      </Link>
    )
  }

  return (
    <Card className="p-4" data-testid="dashboard-stat-semester">
      {content}
    </Card>
  )
}

export function DashboardStatsRow({
  semesterCode,
  planCount,
  riskCount,
  t,
}: DashboardStatsRowProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-3" data-testid="dashboard-stats-row">
      <StatCard
        icon={CalendarDays}
        label={t('dashboard.semester')}
        value={semesterCode ?? '—'}
        hint={t('dashboard.currentTerm')}
      />
      <StatCard
        icon={ClipboardList}
        label={t('dashboard.plans')}
        value={String(planCount)}
        hint={t('dashboard.savedPlans')}
        to="/plans"
        linkLabel={t('dashboard.openPlans')}
      />
      <StatCard
        icon={ShieldAlert}
        label={t('dashboard.riskReports')}
        value={String(riskCount)}
        hint={t('dashboard.analysisHistory')}
        to="/risks"
        linkLabel={t('dashboard.openRisks')}
      />
    </div>
  )
}
