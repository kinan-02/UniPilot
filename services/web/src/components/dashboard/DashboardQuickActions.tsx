import { Link } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  GraduationCap,
  MessageCircle,
  ScrollText,
  ShieldAlert,
  UserCircle,
} from 'lucide-react'

type QuickAction = {
  to: string
  label: string
  description: string
  icon: LucideIcon
  testId: string
}

type DashboardQuickActionsProps = {
  t: (key: string) => string
}

export function DashboardQuickActions({ t }: DashboardQuickActionsProps) {
  const actions: QuickAction[] = [
    {
      to: '/progress',
      label: t('dashboard.graduationProgress'),
      description: t('dashboard.quickActionProgress'),
      icon: GraduationCap,
      testId: 'dashboard-action-progress',
    },
    {
      to: '/transcript',
      label: t('dashboard.transcriptAction'),
      description: t('dashboard.quickActionTranscript'),
      icon: ScrollText,
      testId: 'dashboard-action-transcript',
    },
    {
      to: '/catalog',
      label: t('dashboard.browseCatalog'),
      description: t('dashboard.quickActionCatalog'),
      icon: BookOpen,
      testId: 'dashboard-action-catalog',
    },
    {
      to: '/plans',
      label: t('dashboard.semesterPlans'),
      description: t('dashboard.quickActionPlans'),
      icon: CalendarDays,
      testId: 'dashboard-action-plans',
    },
    {
      to: '/risks',
      label: t('dashboard.riskAnalysis'),
      description: t('dashboard.quickActionRisks'),
      icon: ShieldAlert,
      testId: 'dashboard-action-risks',
    },
    {
      to: '/advisor',
      label: t('dashboard.advisorAction'),
      description: t('dashboard.quickActionAdvisor'),
      icon: MessageCircle,
      testId: 'dashboard-action-advisor',
    },
    {
      to: '/profile',
      label: t('dashboard.profileAction'),
      description: t('dashboard.quickActionProfile'),
      icon: UserCircle,
      testId: 'dashboard-action-profile',
    },
  ]

  return (
    <section className="space-y-3" data-testid="dashboard-quick-actions">
      <div>
        <h2 className="text-base font-semibold">{t('dashboard.quickActions')}</h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">
          {t('dashboard.quickActionsHint')}
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {actions.map(({ to, label, description, icon: Icon, testId }) => (
          <Link
            key={to}
            to={to}
            data-testid={testId}
            className="group flex items-start justify-between gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white p-4 shadow-[var(--shadow-soft)] transition hover:border-[var(--color-primary)]/30 hover:shadow-[var(--shadow-card)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30"
          >
            <div className="flex min-w-0 items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
                <Icon className="h-5 w-5" aria-hidden />
              </div>
              <div className="min-w-0">
                <p className="font-medium">{label}</p>
                <p className="mt-0.5 text-xs leading-snug text-[var(--color-text-muted)] text-pretty">
                  {description}
                </p>
              </div>
            </div>
            <ArrowRight
              className="mt-1 h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-primary)]"
              aria-hidden
            />
          </Link>
        ))}
      </div>
    </section>
  )
}
