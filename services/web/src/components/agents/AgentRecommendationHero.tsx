import { Link } from 'react-router-dom'
import { CalendarDays, Sparkles } from 'lucide-react'
import { cn } from '../../lib/utils'

type CourseCard = { id: string; title?: string; credits?: number }

type AgentRecommendationHeroProps = {
  headline?: string
  rationale?: string
  courseIds: string[]
  courseDetails?: CourseCard[]
  semesterLabel?: string | null
  utilityScore?: string | number | null
  creditsLabel?: string
  utilityScoreLabel?: string
  recommendedLabel: string
  viewCourseLabel: string
  className?: string
  summaryTestId?: string
}

export function AgentRecommendationHero({
  headline,
  rationale,
  courseIds,
  courseDetails = [],
  semesterLabel,
  utilityScore,
  creditsLabel,
  utilityScoreLabel,
  recommendedLabel,
  viewCourseLabel,
  className,
  summaryTestId,
}: AgentRecommendationHeroProps) {
  if (courseIds.length === 0 && !headline) return null

  const scoreDisplay =
    utilityScore != null && utilityScore !== '—' ? String(utilityScore) : null
  const scorePercent =
    scoreDisplay != null && !Number.isNaN(Number(scoreDisplay))
      ? Math.min(100, Math.max(0, Number(scoreDisplay) * 100))
      : null

  return (
    <div
      className={cn(
        'overflow-hidden rounded-2xl border border-[var(--color-border)] bg-gradient-to-br from-white via-white to-[var(--color-primary)]/5 shadow-sm',
        className,
      )}
      data-testid={summaryTestId ?? 'agent-sessions-recommendation-hero'}
    >
      <div className="border-b border-[var(--color-border)]/80 px-5 py-5 sm:px-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
              <Sparkles className="h-3.5 w-3.5 text-[var(--color-primary)]" aria-hidden />
              {recommendedLabel}
            </p>
            {headline ? (
              <h2 className="mt-2 text-lg font-semibold leading-snug text-[var(--color-text)] sm:text-xl">
                {headline}
              </h2>
            ) : null}
            {rationale ? (
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[var(--color-text-muted)]">
                {rationale}
              </p>
            ) : null}
            {semesterLabel ? (
              <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-[var(--color-text-muted)]">
                <CalendarDays className="h-3.5 w-3.5" aria-hidden />
                {semesterLabel}
              </p>
            ) : null}
          </div>

          {scorePercent != null ? (
            <div
              className="flex shrink-0 flex-col items-center rounded-2xl border border-[var(--color-border)] bg-white/90 px-4 py-3"
              aria-label={`Utility score ${scoreDisplay}`}
            >
              <div
                className="relative flex h-14 w-14 items-center justify-center rounded-full"
                style={{
                  background: `conic-gradient(var(--color-primary) ${scorePercent * 3.6}deg, rgb(245 245 244) 0deg)`,
                }}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-xs font-semibold tabular-nums">
                  {Number(scoreDisplay).toFixed(2)}
                </div>
              </div>
              {creditsLabel ? (
                <p className="mt-2 text-[10px] font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                  {creditsLabel}
                </p>
              ) : null}
              {utilityScoreLabel ? (
                <p className="mt-1 text-center text-[10px] text-[var(--color-text-muted)]">{utilityScoreLabel}</p>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>

      {courseIds.length > 0 ? (
        <div className="grid gap-2 px-5 py-4 sm:grid-cols-2 sm:px-6 lg:grid-cols-3">
          {courseIds.map((courseId) => {
            const detail = courseDetails.find((entry) => entry.id === courseId)
            return (
              <Link
                key={courseId}
                to={`/catalog?course=${courseId}`}
                className="group rounded-xl border border-[var(--color-border)] bg-white px-4 py-3 transition hover:border-[var(--color-primary)]/40 hover:shadow-sm"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="font-mono text-sm font-semibold text-[var(--color-primary)]">
                      {courseId}
                    </p>
                    {detail?.title ? (
                      <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-[var(--color-text-muted)]">
                        {detail.title}
                      </p>
                    ) : null}
                  </div>
                  {detail?.credits != null ? (
                    <span className="shrink-0 rounded-full bg-stone-100 px-2 py-0.5 text-[10px] font-medium tabular-nums text-stone-600">
                      {detail.credits}
                    </span>
                  ) : null}
                </div>
                <p className="mt-2 text-xs text-[var(--color-text-muted)] opacity-0 transition group-hover:opacity-100">
                  {viewCourseLabel}
                </p>
              </Link>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}
