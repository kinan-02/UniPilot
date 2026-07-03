import { ChevronDown } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type AgentCollapsibleSectionProps = {
  title: string
  children: ReactNode
  testId?: string
  defaultOpen?: boolean
  description?: string
}

export function AgentCollapsibleSection({
  title,
  children,
  testId,
  defaultOpen = false,
  description,
}: AgentCollapsibleSectionProps) {
  return (
    <details
      className="group overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-sm"
      data-testid={testId}
      open={defaultOpen || undefined}
    >
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 border-b border-transparent bg-[var(--color-surface-muted)]/40 px-4 py-3 transition group-open:border-[var(--color-border)] sm:px-5">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-[var(--color-text)]">{title}</h3>
          {description ? (
            <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{description}</p>
          ) : null}
        </div>
        <ChevronDown
          className="h-4 w-4 shrink-0 text-[var(--color-text-muted)] transition group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <div className={cn('px-4 py-4 text-sm sm:px-5')}>{children}</div>
    </details>
  )
}
