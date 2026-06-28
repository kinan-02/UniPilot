type ProgressPageNavProps = {
  sections: ReadonlyArray<{ id: string; label: string }>
  t: (key: string) => string
}

export function ProgressPageNav({ sections, t }: ProgressPageNavProps) {
  if (sections.length <= 1) return null

  return (
    <nav
      aria-label={t('progress.nav.label')}
      className="sticky top-0 z-20 -mx-1 flex flex-wrap gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface)]/95 px-1 py-2 backdrop-blur-sm"
      data-testid="progress-page-nav"
    >
      {sections.map(({ id, label }) => (
        <a
          key={id}
          href={`#${id}`}
          className="rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs font-medium text-[var(--color-text)] transition hover:border-[var(--color-primary)]/35 hover:bg-[var(--color-surface-muted)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30"
        >
          {label}
        </a>
      ))}
    </nav>
  )
}
