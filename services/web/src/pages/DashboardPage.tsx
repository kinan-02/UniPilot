import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BookOpen } from 'lucide-react'
import { progressApi, plansApi, risksApi } from '../api/endpoints'
import { DashboardLoadingSkeleton } from '../components/dashboard/DashboardLoadingSkeleton'
import { DashboardProgressHero } from '../components/dashboard/DashboardProgressHero'
import { DashboardQuickActions } from '../components/dashboard/DashboardQuickActions'
import { DashboardSetupPrompt } from '../components/dashboard/DashboardSetupPrompt'
import { DashboardStatsRow } from '../components/dashboard/DashboardStatsRow'
import { PageHeader } from '../components/ui/Card'
import { useAuth } from '../auth/AuthContext'
import { useTranslation } from '../i18n'
import { hasStudentProfile, useStudentProfileQuery } from '../lib/studentProfileQuery'

function buildGreeting(programType: string | undefined, t: (key: string) => string): string {
  if (!programType) return t('dashboard.hello')
  return `${t('dashboard.hello')}, ${programType} ${t('dashboard.student')}`
}

function buildStatusLabel(statusSummary: string | undefined, t: (key: string) => string): string {
  if (!statusSummary) return ''
  const statusKey = `progress.statusSummary.${statusSummary}` as const
  const translated = t(statusKey)
  return translated !== statusKey ? translated : statusSummary.replace(/_/g, ' ')
}

export function DashboardPage() {
  const { t } = useTranslation()
  const { user, isLoading: authLoading } = useAuth()
  const profileQuery = useStudentProfileQuery()

  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: progressApi.get,
    enabled: Boolean(profileQuery.data?.profile?.degreeId),
    retry: false,
  })

  const plansQuery = useQuery({
    queryKey: ['plans'],
    queryFn: plansApi.list,
    enabled: hasStudentProfile(profileQuery.data),
  })

  const risksQuery = useQuery({
    queryKey: ['risks'],
    queryFn: risksApi.list,
    enabled: hasStudentProfile(profileQuery.data),
  })

  const profilePending =
    Boolean(user) &&
    profileQuery.data === undefined &&
    !profileQuery.isError &&
    (profileQuery.isLoading || profileQuery.isFetching)

  if (authLoading || profilePending) {
    return <DashboardLoadingSkeleton />
  }

  if (!hasStudentProfile(profileQuery.data)) {
    return (
      <DashboardSetupPrompt
        title={t('dashboard.completeProfile')}
        description={t('dashboard.completeProfileHint')}
        actionLabel={t('dashboard.setupProfile')}
      />
    )
  }

  const profile = profileQuery.data.profile
  const progress = progressQuery.data?.graduationProgress
  const planCount = plansQuery.data?.pagination.total ?? 0
  const riskCount = risksQuery.data?.pagination.total ?? 0
  const statusLabel = buildStatusLabel(progress?.statusSummary, t)

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={buildGreeting(profile?.programType, t)}
        description={t('dashboard.subtitle')}
        action={
          <Link
            to="/transcript"
            className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
          >
            <BookOpen className="h-4 w-4" aria-hidden />
            {t('dashboard.importTranscript')}
          </Link>
        }
      />

      <DashboardProgressHero
        progress={progress}
        progressLoading={progressQuery.isLoading}
        statusLabel={statusLabel}
        t={t}
      />

      <DashboardStatsRow
        semesterCode={profile?.currentSemesterCode}
        planCount={planCount}
        riskCount={riskCount}
        t={t}
      />

      <DashboardQuickActions t={t} />
    </div>
  )
}
