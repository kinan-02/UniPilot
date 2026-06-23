import { useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { Card } from '../ui/Card'
import { Select } from '../ui/Input'
import { TranscriptCourseRow } from './TranscriptCourseRow'
import { compareSemesterCodesDesc, filterTranscriptRecords, groupTranscriptBySemester } from '../../lib/transcript'
import { semesterLabel } from '../../lib/semester'
import { formatCredits } from '../../lib/utils'
import type { CompletedCourse } from '../../types/api'
import type { Locale } from '../../i18n/types'

type TranscriptCourseListProps = {
  records: CompletedCourse[]
  locale: Locale
  t: (key: string) => string
  onDelete: (id: string) => void
  deletingId?: string | null
}

export function TranscriptCourseList({
  records,
  locale,
  t,
  onDelete,
  deletingId = null,
}: TranscriptCourseListProps) {
  const [filter, setFilter] = useState('')
  const [semesterFilter, setSemesterFilter] = useState('')

  const semesterOptions = useMemo(() => {
    const codes = [...new Set(records.map((record) => record.semesterCode))]
    return codes.sort(compareSemesterCodesDesc)
  }, [records])

  const filteredRecords = useMemo(() => {
    const byText = filterTranscriptRecords(records, filter)
    if (!semesterFilter) return byText
    return byText.filter((record) => record.semesterCode === semesterFilter)
  }, [filter, records, semesterFilter])
  const groups = useMemo(() => groupTranscriptBySemester(filteredRecords), [filteredRecords])

  return (
    <div className="space-y-4" data-testid="transcript-course-list">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold">{t('transcript.listTitle')}</h2>
          <p className="mt-1 text-xs text-[var(--color-text-muted)]">
            {filteredRecords.length === records.length
              ? t('transcript.listCount').replace('{count}', String(records.length))
              : `${filteredRecords.length} / ${records.length}`}
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:max-w-md sm:flex-row">
          {semesterOptions.length > 1 ? (
            <Select
              label={t('transcript.filterBySemester')}
              value={semesterFilter}
              onChange={(event) => setSemesterFilter(event.target.value)}
              className="sm:min-w-[180px]"
            >
              <option value="">{t('transcript.filterBySemester')}</option>
              {semesterOptions.map((code) => (
                <option key={code} value={code}>
                  {semesterLabel(code, locale)}
                </option>
              ))}
            </Select>
          ) : null}
          <div className="relative flex-1">
          <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
          <input
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder={t('transcript.filterPlaceholder')}
            className="h-10 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-3 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
            data-testid="transcript-filter-input"
          />
          </div>
        </div>
      </div>

      {groups.length === 0 ? (
        <Card className="border-dashed text-center text-sm text-[var(--color-text-muted)]">
          {t('common.noResults')}
        </Card>
      ) : (
        groups.map((group) => (
          <Card key={group.semesterCode} className="overflow-hidden p-0">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]/50 px-5 py-3">
              <div>
                <p className="text-sm font-medium">{semesterLabel(group.semesterCode, locale)}</p>
                <p className="text-xs text-[var(--color-text-muted)]">{group.semesterCode}</p>
              </div>
              <p className="text-xs font-medium tabular-nums text-[var(--color-text-muted)]">
                {t('transcript.semesterCredits').replace(
                  '{credits}',
                  formatCredits(group.semesterCredits),
                )}
              </p>
            </div>
            <div className="divide-y divide-[var(--color-border)]">
              {group.courses.map((record) => (
                <TranscriptCourseRow
                  key={record.id}
                  record={record}
                  t={t}
                  onDelete={onDelete}
                  deleting={deletingId === record.id}
                />
              ))}
            </div>
          </Card>
        ))
      )}
    </div>
  )
}
