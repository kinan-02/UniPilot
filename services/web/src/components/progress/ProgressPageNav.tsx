import { cn } from '../../lib/utils'

type ProgressPageNavProps = {
  sections: ReadonlyArray<{ id: string; label: string }>
  t: (key: string) => string
}

export function ProgressPageNav({ sections, t }: ProgressPageNavProps) {
  if (sections.length <= 1) return null

  return (
    <nav
      aria-label={t('progress.nav.label')}
      className="sticky top-0 z-20 -mx-1 flex gap-2 overflow-x-auto border-b border-[var(--color-border)] bg-[var(--color-surface)]/95 px-1 py-2.5 backdrop-blur-sm [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      data-testid="progress-page-nav"
    >
      {sections.map(({ id, label }, index) => (
        <a
          key={id}
          href={`#${id}`}
          className={cn(
            'shrink-0 rounded-full border px-3.5 py-1.5 text-xs font-medium transition',
            'border-[var(--color-border)] bg-white text-[var(--color-text)]',
            'hover:border-[var(--color-primary)]/35 hover:bg-[var(--color-surface-muted)]',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30',
            index === 0 && 'border-[var(--color-primary)]/25 bg-[var(--color-primary)]/5 text-[var(--color-primary)]',
          )}
        >
          {label}
        </a>
      ))}
    </nav>
  )
}
