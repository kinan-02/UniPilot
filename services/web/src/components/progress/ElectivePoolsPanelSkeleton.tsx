import { Card } from '../ui/Card'

export function ElectivePoolsPanelSkeleton() {
  return (
    <Card className="overflow-hidden p-0" data-testid="elective-pools-panel-skeleton">
      <div className="border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]/60 px-5 py-5 sm:px-6">
        <div className="h-4 w-32 animate-pulse rounded bg-stone-200" />
        <div className="mt-3 h-7 w-64 max-w-full animate-pulse rounded bg-stone-200" />
        <div className="mt-2 h-4 w-full max-w-xl animate-pulse rounded bg-stone-100" />
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="h-20 animate-pulse rounded-xl border border-[var(--color-border)] bg-white/70"
            />
          ))}
        </div>
      </div>
      <div className="grid gap-4 px-5 py-5 sm:grid-cols-2 sm:px-6 xl:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <div
            key={index}
            className="h-48 animate-pulse rounded-xl border border-[var(--color-border)] bg-white/80"
          />
        ))}
      </div>
    </Card>
  )
}
