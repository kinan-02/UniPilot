import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Trash2 } from 'lucide-react'
import { Badge } from '../ui/Card'
import { Button } from '../ui/Button'
import { formatCredits } from '../../lib/utils'
import {
  gradeBadgeTone,
  isManualTranscriptRecord,
  sourceBadgeTone,
} from '../../lib/transcript'
import type { CompletedCourse } from '../../types/api'

type TranscriptCourseRowProps = {
  record: CompletedCourse
  t: (key: string) => string
  onDelete: (id: string) => void
  deleting?: boolean
}

function sourceLabel(source: string, t: (key: string) => string): string {
  const key = `transcript.source.${source}` as const
  const translated = t(key)
  return translated !== key ? translated : source
}

export function TranscriptCourseRow({
  record,
  t,
  onDelete,
  deleting = false,
}: TranscriptCourseRowProps) {
  const [confirming, setConfirming] = useState(false)
  const canDelete = isManualTranscriptRecord(record)

  return (
    <div
      className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between"
      data-testid={`transcript-row-${record.courseNumber ?? record.id}`}
    >
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/catalog?course=${encodeURIComponent(record.courseNumber ?? '')}`}
            className="font-mono text-sm font-medium text-[var(--color-primary)] hover:underline"
          >
            {record.courseNumber ?? record.courseId}
          </Link>
          <Badge tone={gradeBadgeTone(record.grade)}>
            {t('transcript.gradeLabel').replace('{grade}', String(record.grade))}
          </Badge>
        </div>
        <p className="mt-1 text-sm text-[var(--color-text)]">{record.courseTitle ?? '—'}</p>
        <p className="mt-1 text-xs text-[var(--color-text-muted)]">
          {formatCredits(record.creditsEarned)} {t('common.credits')}
          {record.attempt > 1 ? ` · Attempt ${record.attempt}` : ''}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <Badge tone={sourceBadgeTone(record.source)}>{sourceLabel(record.source, t)}</Badge>
        {canDelete ? (
          confirming ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-[var(--color-text-muted)]">{t('transcript.deleteConfirm')}</span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setConfirming(false)}
                disabled={deleting}
              >
                {t('common.cancel')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                size="sm"
                loading={deleting}
                onClick={() => {
                  onDelete(record.id)
                  setConfirming(false)
                }}
              >
                {t('transcript.delete')}
              </Button>
            </div>
          ) : (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setConfirming(true)}
              aria-label={t('transcript.delete')}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )
        ) : null}
      </div>
    </div>
  )
}
