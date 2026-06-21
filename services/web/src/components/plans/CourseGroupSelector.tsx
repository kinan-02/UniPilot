import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { catalogApi } from '../../api/endpoints'
import { useTranslation } from '../../i18n'
import {
  buildSelectedGroupsFromOptions,
  groupOptionsFromOffering,
  type GroupOption,
} from '../../lib/scheduleGroups'
import type { SelectedGroups } from '../../types/api'
import { Button } from '../ui/Button'
import { Spinner } from '../ui/Card'

type CourseGroupSelectorProps = {
  courseNumber: string
  courseTitle: string
  academicYear?: number
  semesterCode?: number
  selectedGroups?: SelectedGroups
  onClose: () => void
  onSave: (groups: SelectedGroups) => void
}

const SLOT_ORDER = ['lecture', 'tutorial', 'lab', 'project'] as const

const emptyGroups = (): SelectedGroups => ({
  lecture: null,
  tutorial: null,
  lab: null,
  project: null,
})

export function CourseGroupSelector({
  courseNumber,
  courseTitle,
  academicYear,
  semesterCode,
  selectedGroups,
  onClose,
  onSave,
}: CourseGroupSelectorProps) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<SelectedGroups>(selectedGroups ?? emptyGroups())

  useEffect(() => {
    setDraft(selectedGroups ?? emptyGroups())
  }, [selectedGroups, courseNumber])

  const offeringsQuery = useQuery({
    queryKey: ['course-groups', courseNumber, academicYear, semesterCode],
    queryFn: () =>
      catalogApi.offerings(courseNumber, {
        academicYear,
        semesterCode,
      }),
    enabled: Boolean(courseNumber && academicYear && semesterCode),
  })

  const offering = offeringsQuery.data?.offerings?.[0]
  const options = groupOptionsFromOffering(offering?.scheduleGroups ?? [])
  const optionsBySlot = SLOT_ORDER.reduce<Record<string, GroupOption[]>>((acc, slot) => {
    acc[slot] = options.filter((opt) => opt.slotKey === slot)
    return acc
  }, {})

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/40 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
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
            <p className="mt-1 text-xs text-[var(--color-text-muted)]">{t('planner.groupsHint')}</p>
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
          <p className="text-sm text-[var(--color-text-muted)]">{t('planner.noScheduleData')}</p>
        ) : (
          <div className="space-y-4">
            {SLOT_ORDER.map((slotKey) => {
              const slotOptions = optionsBySlot[slotKey] ?? []
              if (!slotOptions.length) return null
              return (
                <div key={slotKey}>
                  <label className="mb-1.5 block text-xs font-medium text-[var(--color-text-muted)]">
                    {t(`planner.slot.${slotKey}` as 'planner.slot.lecture')}
                  </label>
                  <select
                    className="h-10 w-full rounded-xl border border-[var(--color-border)] bg-white px-3 text-sm"
                    value={draft[slotKey] ?? ''}
                    onChange={(e) => {
                      const value = e.target.value
                      setDraft((current) =>
                        buildSelectedGroupsFromOptions(
                          current,
                          slotKey,
                          value === '' ? null : Number(value),
                        ),
                      )
                    }}
                  >
                    <option value="">{t('planner.groupsDefault')}</option>
                    {slotOptions.map((opt) => (
                      <option key={`${slotKey}-${opt.index}`} value={opt.index}>
                        {opt.label} — {opt.day} {opt.timeRange}
                      </option>
                    ))}
                  </select>
                </div>
              )
            })}
          </div>
        )}

        <div className="mt-6 flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => onSave(draft)}>{t('common.save')}</Button>
        </div>
      </div>
    </div>
  )
}
