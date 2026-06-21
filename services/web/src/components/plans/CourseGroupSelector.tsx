import { useQuery } from '@tanstack/react-query'
import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, X } from 'lucide-react'
import { catalogApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import {
  extractLessonOptions,
  groupLessonOptionsByType,
  LESSON_TYPE_ORDER,
  lessonSelectionSummary,
  migrateLegacySelectedGroups,
  selectedEventsFromDraft,
  type LessonOption,
} from '../../lib/lessonEvents'
import type { SelectedGroups, SelectedLessonEvent } from '../../types/api'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Card'

type CourseGroupSelectorProps = {
  courseNumber: string
  courseTitle: string
  academicYear?: number
  semesterCode?: number
  selectedLessonEvents?: SelectedLessonEvent[]
  selectedGroups?: SelectedGroups
  onClose: () => void
  onSave: (events: SelectedLessonEvent[]) => void
  onPreview?: (option: LessonOption | null) => void
}

export function CourseGroupSelector({
  courseNumber,
  courseTitle,
  academicYear,
  semesterCode,
  selectedLessonEvents,
  selectedGroups,
  onClose,
  onSave,
  onPreview,
}: CourseGroupSelectorProps) {
  const { t } = useTranslation()
  const [draftIds, setDraftIds] = useState<Set<string>>(new Set())

  const offeringsQuery = useQuery({
    queryKey: ['course-lessons', courseNumber, academicYear, semesterCode],
    queryFn: () =>
      catalogApi.offerings(courseNumber, {
        academicYear,
        semesterCode,
      }),
    enabled: Boolean(courseNumber && academicYear && semesterCode),
  })

  const offering = offeringsQuery.data?.offerings?.[0]
  const options = useMemo(
    () => extractLessonOptions(offering, courseNumber),
    [offering, courseNumber],
  )
  const optionsByType = useMemo(() => groupLessonOptionsByType(options), [options])

  useEffect(() => {
    if (selectedLessonEvents?.length) {
      setDraftIds(new Set(selectedLessonEvents.map((event) => event.eventId)))
      return
    }
    const migrated = migrateLegacySelectedGroups(selectedGroups, options)
    setDraftIds(new Set(migrated.map((event) => event.eventId)))
  }, [selectedLessonEvents, selectedGroups, courseNumber, options])

  const toggleOption = (option: LessonOption) => {
    setDraftIds((current) => {
      const next = new Set(current)
      if (next.has(option.eventId)) {
        next.delete(option.eventId)
      } else {
        const sameType = options.filter((item) => item.type === option.type)
        if (sameType.length > 1) {
          sameType.forEach((item) => next.delete(item.eventId))
        }
        next.add(option.eventId)
      }
      return next
    })
  }

  const clearSelection = () => {
    setDraftIds(new Set())
    onPreview?.(null)
  }

  const renderOption = (option: LessonOption) => {
    const checked = draftIds.has(option.eventId)
    const labelParts = [
      option.group ? `${t('planner.groupLabel')} ${option.group}` : option.slotTypeLabel,
      option.day,
      option.timeRange || `${option.startTime}-${option.endTime}`,
      option.location,
      option.instructor,
    ].filter(Boolean)

    return (
      <label
        key={option.eventId}
        className="flex cursor-pointer items-start gap-3 rounded-xl border border-[var(--color-border)] px-3 py-2 hover:bg-[var(--color-surface-muted)]"
        onMouseEnter={() => onPreview?.(option)}
        onMouseLeave={() => onPreview?.(null)}
        onFocus={() => onPreview?.(option)}
        onBlur={() => onPreview?.(null)}
      >
        <input
          type="checkbox"
          className="mt-1"
          checked={checked}
          onChange={() => toggleOption(option)}
        />
        <span className="min-w-0 flex-1 text-sm">
          <span className="block">{labelParts.join(' · ')}</span>
          {option.incomplete ? (
            <span className="mt-1 flex items-center gap-1 text-xs text-[var(--color-warning)]">
              <AlertTriangle className="h-3 w-3" />
              {t('planner.incompleteLessonData')}
            </span>
          ) : null}
        </span>
      </label>
    )
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={t('planner.chooseLessons')}
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <p className="font-mono text-xs text-[var(--color-primary)]">{courseNumber}</p>
            <h2 className="text-base font-semibold">{courseTitle}</h2>
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{t('planner.lessonSelectionHint')}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {offeringsQuery.isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner />
          </div>
        ) : !options.length ? (
          <p className="text-sm text-[var(--color-text-muted)]">{t('planner.noLessonOptions')}</p>
        ) : (
          <div className="space-y-4">
            {LESSON_TYPE_ORDER.map((type) => {
              const typeOptions = optionsByType[type] ?? []
              if (!typeOptions.length) return null
              return (
                <div key={type}>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-[var(--color-text-muted)]">
                    {t(`planner.slot.${type}` as 'planner.slot.lecture')}
                  </h3>
                  <div className="space-y-2">{typeOptions.map(renderOption)}</div>
                </div>
              )
            })}
            {draftIds.size === 0 ? (
              <p className="text-xs text-[var(--color-warning)]">{t('planner.chooseLessonsWarning')}</p>
            ) : (
              <p className="text-xs text-[var(--color-primary)]">
                {lessonSelectionSummary(options, selectedEventsFromDraft(draftIds, options), t)}
              </p>
            )}
          </div>
        )}

        <div className="mt-6 flex justify-between gap-2">
          <Button variant="secondary" onClick={clearSelection}>
            {t('planner.clearLessonSelection')}
          </Button>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => onSave(selectedEventsFromDraft(draftIds, options))}>
              {t('common.save')}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
