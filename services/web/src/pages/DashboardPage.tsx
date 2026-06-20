import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { ArrowRight, BookOpen, CalendarDays, GraduationCap, ShieldAlert } from 'lucide-react'
import { profileApi, progressApi, plansApi, risksApi } from '../api/endpoints'
import { isAuthError } from '../auth/AuthContext'
import { Badge, Card, PageHeader, Spinner } from '../components/ui/Card'
import { formatPercent } from '../lib/utils'

export function DashboardPage() {
  const profileQuery = useQuery({
    queryKey: ['profile'],
    queryFn: profileApi.get,
    retry: false,
  })

  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: progressApi.get,
    enabled: Boolean(profileQuery.data?.profile?.degreeId),
  })

  const plansQuery = useQuery({
    queryKey: ['plans'],
    queryFn: plansApi.list,
  })

  const risksQuery = useQuery({
    queryKey: ['risks'],
    queryFn: risksApi.list,
  })

  if (profileQuery.isLoading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    )
  }

  if (profileQuery.isError && isAuthError(profileQuery.error) && profileQuery.error.status === 404) {
    return (
      <Card className="animate-fade-in text-center">
        <h2 className="text-lg font-semibold">Complete your profile</h2>
        <p className="mt-2 text-sm text-[var(--color-text-muted)]">
          Add your degree program to unlock progress tracking and semester planning.
        </p>
        <Link
          to="/onboarding"
          className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-[var(--color-primary)]"
        >
          Set up profile
          <ArrowRight className="h-4 w-4" />
        </Link>
      </Card>
    )
  }

  const profile = profileQuery.data?.profile
  const progress = progressQuery.data?.graduationProgress
  const planCount = plansQuery.data?.pagination.total ?? 0
  const riskCount = risksQuery.data?.pagination.total ?? 0

  const quickLinks = [
    { to: '/catalog', label: 'Browse catalog', icon: BookOpen },
    { to: '/plans', label: 'Semester plans', icon: CalendarDays },
    { to: '/progress', label: 'Graduation progress', icon: GraduationCap },
    { to: '/risks', label: 'Risk analysis', icon: ShieldAlert },
  ]

  return (
    <div className="animate-fade-in space-y-8">
      <PageHeader
        title={`Hello${profile?.programType ? `, ${profile.programType} student` : ''}`}
        description="Your academic command center — track progress, explore courses, and plan ahead."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Completion
          </p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">
            {progress ? formatPercent(progress.completionPercentage) : '—'}
          </p>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">
            {progress
              ? `${progress.completedCredits} / ${progress.totalRequiredCredits} credits`
              : 'Add a degree to track progress'}
          </p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Semester
          </p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">
            {profile?.currentSemesterCode ?? '—'}
          </p>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">Current term</p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Plans
          </p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">{planCount}</p>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">Saved semester plans</p>
        </Card>
        <Card>
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
            Risk reports
          </p>
          <p className="mt-2 text-3xl font-semibold tracking-tight">{riskCount}</p>
          <p className="mt-1 text-sm text-[var(--color-text-muted)]">Analysis history</p>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {quickLinks.map(({ to, label, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            className="group flex items-center justify-between rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white p-5 shadow-[var(--shadow-soft)] transition hover:border-[var(--color-primary)]/30 hover:shadow-[var(--shadow-card)]"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--color-surface-muted)] text-[var(--color-primary)]">
                <Icon className="h-5 w-5" />
              </div>
              <span className="font-medium">{label}</span>
            </div>
            <ArrowRight className="h-4 w-4 text-[var(--color-text-muted)] transition group-hover:translate-x-0.5 group-hover:text-[var(--color-primary)]" />
          </Link>
        ))}
      </div>

      {progress?.statusSummary ? (
        <Card>
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Degree status</p>
              <p className="mt-1 text-sm text-[var(--color-text-muted)]">
                {progress.degreeName ?? progress.degreeCode}
              </p>
            </div>
            <Badge tone={progress.statusSummary === 'complete' ? 'success' : 'primary'}>
              {progress.statusSummary.replace(/_/g, ' ')}
            </Badge>
          </div>
        </Card>
      ) : null}
    </div>
  )
}
