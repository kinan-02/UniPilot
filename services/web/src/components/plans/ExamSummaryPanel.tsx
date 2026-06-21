import { CalendarDays, Clock } from 'lucide-react'
import type { ExamSummary, ExamSummaryItem } from '../../types/api'
import { useTranslation } from '../../i18n'
import {
  daysBetweenDates,
  formatExamDate,
  groupExamsByMoed,
} from '../../lib/examDisplay'
import { courseColorStyles } from '../../lib/plannerColors'
import { cn } from '../../lib/utils'
import { Badge, Card } from '../ui/Card'

type ExamSummaryPanelProps = {
  summary?: ExamSummary
  highlightedCourseNumber?: string | null
  highlightedCourseNumbers?: Set<string>
  onExamHover?: (courseNumber: string | null) => void
  className?: string
}

function groupExamsByDate(exams: ExamSummaryItem[]): Array<[string, ExamSummaryItem[]]> {
  const byDate = new Map<string, ExamSummaryItem[]>()
  for (const exam of exams) {
    const date = exam.date ?? ''
    if (!date) continue
    const bucket = byDate.get(date) ?? []
    bucket.push(exam)
    byDate.set(date, bucket)
  }
  return [...byDate.entries()].sort(([left], [right]) => left.localeCompare(right))
}

function ExamCard({
  exam,
  highlightedCourseNumber,
  highlightedCourseNumbers,
  onExamHover,
  locale,
}: {
  exam: ExamSummaryItem
  highlightedCourseNumber?: string | null
  highlightedCourseNumbers?: Set<string>
  onExamHover?: (courseNumber: string | null) => void
  locale: 'he' | 'en'
}) {
  const { t } = useTranslation()
  const courseNumber = exam.courseNumber ?? ''
  const colorStyles = courseColorStyles(courseNumber)
  const highlighted =
    highlightedCourseNumber === courseNumber || Boolean(highlightedCourseNumbers?.has(courseNumber))

  return (
    <div
      role="button"
      tabIndex={0}
      onMouseEnter={() => onExamHover?.(courseNumber || null)}
      onMouseLeave={() => onExamHover?.(null)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onExamHover?.(courseNumber || null)
        }
      }}
      className={cn(
        'min-w-[220px] flex-1 rounded-lg border px-3 py-2.5 text-start shadow-sm transition hover:brightness-[0.98]',
        highlighted && 'ring-2 ring-[var(--color-primary)]/60',
      )}
      style={colorStyles}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="font-mono text-xs font-bold">{courseNumber}</p>
        {exam.startTime ? (
          <span className="inline-flex shrink-0 items-center gap-1 rounded-md bg-white/60 px-1.5 py-0.5 text-[10px] font-medium">
            <Clock className="h-3 w-3" aria-hidden />
            {exam.startTime}
          </span>
        ) : null}
      </div>
      <p className="mt-1 text-sm font-medium leading-snug">{exam.courseName}</p>
      <p className="mt-2 inline-flex items-center gap-1 text-xs opacity-90">
        <CalendarDays className="h-3 w-3" aria-hidden />
        {exam.date ? formatExamDate(exam.date, locale) : t('planner.examUnknown')}
      </p>
    </div>
  )
}

function MoedExamSection({
  title,
  exams,
  highlightedCourseNumber,
  highlightedCourseNumbers,
  onExamHover,
  locale,
}: {
  title: string
  exams: ExamSummaryItem[]
  highlightedCourseNumber?: string | null
  highlightedCourseNumbers?: Set<string>
  onExamHover?: (courseNumber: string | null) => void
  locale: 'he' | 'en'
}) {
  const { t } = useTranslation()
  if (!exams.length) return null

  const byDate = groupExamsByDate(exams)

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 p-3">
      <header className="mb-3 flex items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-[var(--color-text)]">{title}</h4>
        <Badge tone="neutral">{exams.length}</Badge>
      </header>

      <div className="space-y-4">
        {byDate.map(([date, dateExams], index) => {
          const previousDate = byDate[index - 1]?.[0]
          const gapDays =
            previousDate && date ? daysBetweenDates(previousDate, date) : 0

          return (
            <div key={date}>
              {gapDays > 0 ? (
                <div className="mb-3 flex items-center gap-2 text-[10px] text-[var(--color-text-muted)]">
                  <span className="h-px flex-1 border-t border-dashed border-[var(--color-border)]" />
                  <span>{t('planner.examDaysUntilNext').replace('{count}', String(gapDays))}</span>
                  <span className="h-px flex-1 border-t border-dashed border-[var(--color-border)]" />
                </div>
              ) : null}

              <p className="mb-2 text-xs font-semibold text-[var(--color-text-muted)]">
                {formatExamDate(date, locale)}
              </p>

              <div className="flex flex-wrap gap-2">
                {dateExams.map((exam) => (
                  <ExamCard
                    key={`${exam.courseNumber}-${exam.moed}-${exam.date}-${exam.startTime}`}
                    exam={exam}
                    highlightedCourseNumber={highlightedCourseNumber}
                    highlightedCourseNumbers={highlightedCourseNumbers}
                    onExamHover={onExamHover}
                    locale={locale}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

export function ExamSummaryPanel({
  summary,
  highlightedCourseNumber,
  highlightedCourseNumbers,
  onExamHover,
  className,
}: ExamSummaryPanelProps) {
  const { t, locale } = useTranslation()
  const exams = (summary?.exams ?? []).filter((exam) => exam.date)
  const warnings = summary?.warnings ?? []
  const conflictWarnings = warnings.filter((warning) => warning.type === 'same_day_exams')

  if (!exams.length) {
    return (
      <Card className={className}>
        <h3 className="text-sm font-semibold">{t('planner.examsTitle')}</h3>
        <p className="mt-2 text-xs text-[var(--color-text-muted)]">{t('planner.noExams')}</p>
      </Card>
    )
  }

  const grouped = groupExamsByMoed(exams)
  const moedSections = [
    { key: 'a', title: t('planner.moedA'), exams: grouped.moedA },
    { key: 'b', title: t('planner.moedB'), exams: grouped.moedB },
    { key: 'other', title: t('planner.moedOther'), exams: grouped.other },
  ].filter((section) => section.exams.length)

  return (
    <Card className={className}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{t('planner.examsTitle')}</h3>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">{t('planner.examsSubtitle')}</p>
        </div>
        <Badge tone="neutral">{exams.length}</Badge>
      </div>

      {conflictWarnings.length ? (
        <div className="mb-4 rounded-lg border border-[var(--color-warning)]/40 bg-amber-50 px-3 py-2">
          <p className="text-xs font-medium text-[var(--color-warning)]">{t('planner.examConflictTitle')}</p>
          {conflictWarnings.map((warning, index) => (
            <p key={index} className="mt-0.5 text-xs text-[var(--color-warning)]">
              {warning.message ??
                `${t('planner.examSameDayConflict')} ${warning.date ?? ''}: ${(warning.courseNumbers ?? []).join(', ')}`}
            </p>
          ))}
        </div>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {moedSections.map((section) => (
          <MoedExamSection
            key={section.key}
            title={section.title}
            exams={section.exams}
            highlightedCourseNumber={highlightedCourseNumber}
            highlightedCourseNumbers={highlightedCourseNumbers}
            onExamHover={onExamHover}
            locale={locale}
          />
        ))}
      </div>
    </Card>
  )
}
