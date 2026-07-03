import { BookOpen, Gauge, Layers } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

type MetricItem = {
  label: string
  value: string
  hint?: string
  icon: LucideIcon
}

type AgentPlanMetricsProps = {
  courseCount: number
  totalCredits: number | string
  utilityScore?: number | string | null
  coursesLabel: string
  creditsLabel: string
  utilityLabel: string
}

export function AgentPlanMetrics({
  courseCount,
  totalCredits,
  utilityScore,
  coursesLabel,
  creditsLabel,
  utilityLabel,
}: AgentPlanMetricsProps) {
  const metrics: MetricItem[] = [
    {
      icon: Layers,
      label: coursesLabel,
      value: String(courseCount),
    },
    {
      icon: BookOpen,
      label: creditsLabel,
      value: String(totalCredits),
    },
    {
      icon: Gauge,
      label: utilityLabel,
      value: utilityScore != null ? Number(utilityScore).toFixed(2) : '—',
    },
  ]

  return (
    <div
      className="grid gap-3 sm:grid-cols-3"
      data-testid="agent-sessions-plan-metrics"
    >
      {metrics.map((metric) => (
        <div
          key={metric.label}
          className="rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 shadow-sm"
        >
          <div className="flex items-center gap-2">
            <metric.icon className="h-4 w-4 text-[var(--color-primary)]" aria-hidden />
            <p className="text-xs font-medium text-[var(--color-text-muted)]">{metric.label}</p>
          </div>
          <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight">{metric.value}</p>
        </div>
      ))}
    </div>
  )
}
