import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type AgentSectionProps = {
  title: string
  children: ReactNode
  testId?: string
  accent?: 'default' | 'primary' | 'success' | 'warning' | 'danger' | 'info'
  description?: string
}

const accentBorder: Record<NonNullable<AgentSectionProps['accent']>, string> = {
  default: 'border-l-stone-300',
  primary: 'border-l-[var(--color-primary)]',
  success: 'border-l-emerald-500',
  warning: 'border-l-amber-500',
  danger: 'border-l-rose-500',
  info: 'border-l-sky-500',
}

export function AgentSection({
  title,
  children,
  testId,
  accent = 'default',
  description,
}: AgentSectionProps) {
  return (
    <section
      className={cn(
        'overflow-hidden rounded-2xl border border-[var(--color-border)] bg-white shadow-sm',
        'border-s-4',
        accentBorder[accent],
      )}
      data-testid={testId}
    >
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]/40 px-4 py-3 sm:px-5">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{title}</h3>
        {description ? (
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{description}</p>
        ) : null}
      </header>
      <div className="px-4 py-4 text-sm sm:px-5">{children}</div>
    </section>
  )
}
