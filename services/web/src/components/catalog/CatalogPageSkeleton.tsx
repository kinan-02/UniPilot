import { Card } from '../ui/Card'

export function CatalogPageSkeleton() {
  return (
    <div className="space-y-6" data-testid="catalog-page-skeleton">
      <Card>
        <div className="grid gap-4 lg:grid-cols-[1fr_240px]">
          <div className="h-11 animate-pulse rounded-xl bg-stone-100" />
          <div className="h-11 animate-pulse rounded-xl bg-stone-100" />
        </div>
      </Card>
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Card className="space-y-3 p-0 overflow-hidden">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="border-b border-[var(--color-border)] px-5 py-4 last:border-0">
              <div className="h-4 w-24 animate-pulse rounded bg-stone-200" />
              <div className="mt-2 h-4 w-3/4 animate-pulse rounded bg-stone-100" />
            </div>
          ))}
        </Card>
        <Card className="hidden h-80 animate-pulse bg-stone-50 lg:block" />
      </div>
    </div>
  )
}
