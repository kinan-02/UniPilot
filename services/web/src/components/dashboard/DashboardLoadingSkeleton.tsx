import { Card } from '../ui/Card'

function Shimmer({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-[var(--color-surface-muted)] ${className ?? ''}`}
      aria-hidden
    />
  )
}

export function DashboardLoadingSkeleton() {
  return (
    <div className="animate-fade-in space-y-6" data-testid="dashboard-loading-skeleton">
      <div className="space-y-2">
        <Shimmer className="h-8 w-56" />
        <Shimmer className="h-4 w-80 max-w-full" />
      </div>
      <Card className="overflow-hidden p-0">
        <div className="space-y-4 px-6 py-5">
          <Shimmer className="h-6 w-32 rounded-full" />
          <Shimmer className="h-12 w-48" />
          <Shimmer className="h-3 w-full rounded-full" />
        </div>
      </Card>
      <div className="grid gap-4 sm:grid-cols-3">
        <Shimmer className="h-24" />
        <Shimmer className="h-24" />
        <Shimmer className="h-24" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Shimmer className="h-16" />
        <Shimmer className="h-16" />
        <Shimmer className="h-16" />
        <Shimmer className="h-16" />
        <Shimmer className="h-16" />
        <Shimmer className="h-16" />
      </div>
    </div>
  )
}
