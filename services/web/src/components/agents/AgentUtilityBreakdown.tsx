import { AgentSection } from './AgentSection'

type UtilityComponents = Record<string, number>

type AgentUtilityBreakdownProps = {
  title: string
  components: UtilityComponents
  labels: Record<string, string>
}

const COMPONENT_ORDER = [
  'progress_gain',
  'path_alignment',
  'prereq_safety',
  'load_balance',
  'preference_match',
  'risk_penalty',
]

export function AgentUtilityBreakdown({ title, components, labels }: AgentUtilityBreakdownProps) {
  const entries = COMPONENT_ORDER.filter((key) => components[key] != null).map((key) => ({
    key,
    value: components[key],
    label: labels[key] ?? key.replace(/_/g, ' '),
  }))

  if (entries.length === 0) return null

  return (
    <AgentSection title={title} testId="agent-sessions-utility-breakdown">
      <ul className="space-y-3">
        {entries.map((entry) => {
          const percent = Math.min(100, Math.max(0, entry.value * 100))
          const isPenalty = entry.key === 'risk_penalty'
          return (
            <li key={entry.key}>
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="font-medium text-[var(--color-text)]">{entry.label}</span>
                <span className="tabular-nums text-[var(--color-text-muted)]">
                  {entry.value.toFixed(2)}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-stone-100">
                <div
                  className={
                    isPenalty
                      ? 'h-full rounded-full bg-rose-400/80'
                      : 'h-full rounded-full bg-[var(--color-primary)]'
                  }
                  style={{ width: `${percent}%` }}
                />
              </div>
            </li>
          )
        })}
      </ul>
    </AgentSection>
  )
}
