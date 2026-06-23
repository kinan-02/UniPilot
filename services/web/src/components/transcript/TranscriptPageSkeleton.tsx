import { Card, Spinner } from '../ui/Card'

export function TranscriptPageSkeleton() {
  return (
    <div className="animate-fade-in space-y-6" data-testid="transcript-page-skeleton">
      <div className="mb-8 space-y-2">
        <div className="h-8 w-48 rounded-lg bg-stone-100" />
        <div className="h-4 w-full max-w-xl rounded-lg bg-stone-100" />
      </div>
      <Card className="space-y-4">
        <div className="h-4 w-40 rounded bg-stone-100" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-11 rounded-xl bg-stone-100" />
          ))}
        </div>
        <div className="h-10 w-36 rounded-xl bg-stone-100" />
      </Card>
      <div className="flex justify-center py-16">
        <Spinner />
      </div>
    </div>
  )
}
