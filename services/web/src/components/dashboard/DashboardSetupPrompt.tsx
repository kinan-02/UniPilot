import { Link } from 'react-router-dom'
import { ArrowRight, GraduationCap } from 'lucide-react'
import { Card } from '../ui/Card'

type DashboardSetupPromptProps = {
  title: string
  description: string
  actionLabel: string
}

export function DashboardSetupPrompt({
  title,
  description,
  actionLabel,
}: DashboardSetupPromptProps) {
  return (
    <Card
      className="animate-fade-in overflow-hidden p-0 text-center"
      data-testid="dashboard-setup-prompt"
    >
      <div className="bg-gradient-to-br from-[var(--color-primary)]/5 via-white to-[var(--color-surface-muted)]/40 px-6 py-10">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
          <GraduationCap className="h-7 w-7" aria-hidden />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-balance">{title}</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-[var(--color-text-muted)] text-pretty">
          {description}
        </p>
        <Link
          to="/onboarding"
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[var(--color-primary)] px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-95"
        >
          {actionLabel}
          <ArrowRight className="h-4 w-4" aria-hidden />
        </Link>
      </div>
    </Card>
  )
}
