import { Card } from '../ui/Card'

function Shimmer({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-[var(--color-surface-muted)] ${className ?? ''}`}
      aria-hidden
    />
  )
}

export function ProgressLoadingSkeleton() {
  return (
    <div className="animate-fade-in space-y-6" data-testid="progress-loading-skeleton">
      <div className="space-y-2">
        <Shimmer className="h-8 w-48" />
        <Shimmer className="h-4 w-72 max-w-full" />
      </div>
      <Card className="overflow-hidden p-0">
        <div className="space-y-4 px-6 py-5">
          <div className="flex justify-between gap-3">
            <Shimmer className="h-4 w-40" />
            <Shimmer className="h-6 w-24 rounded-full" />
          </div>
          <Shimmer className="h-12 w-56" />
          <Shimmer className="h-3 w-full rounded-full" />
        </div>
        <div className="grid gap-3 border-t border-[var(--color-border)] px-6 py-5 sm:grid-cols-3">
          <Shimmer className="h-20" />
          <Shimmer className="h-20" />
          <Shimmer className="h-20" />
        </div>
      </Card>
      <Shimmer className="h-10 w-full max-w-xl rounded-full" />
      <Card className="space-y-3 p-5">
        <Shimmer className="h-5 w-44" />
        <Shimmer className="h-16 w-full" />
        <Shimmer className="h-16 w-full" />
      </Card>
    </div>
  )
}
