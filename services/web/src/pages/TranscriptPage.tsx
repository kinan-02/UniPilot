import { Link } from 'react-router-dom'
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { GraduationCap, Info } from 'lucide-react'
import { progressApi, transcriptApi } from '../api/endpoints'
import { TranscriptAddCourseForm } from '../components/transcript/TranscriptAddCourseForm'
import { TranscriptCourseList } from '../components/transcript/TranscriptCourseList'
import { TranscriptPageSkeleton } from '../components/transcript/TranscriptPageSkeleton'
import { TranscriptSummaryCard } from '../components/transcript/TranscriptSummaryCard'
import { Card, EmptyState, PageHeader } from '../components/ui/Card'
import { TRANSCRIPT_QUERY_KEY, useTranscriptRecords } from '../hooks/useTranscriptRecords'
import { useTranslation } from '../i18n'
import { defaultSemesterCode } from '../lib/semester'
import { computeTranscriptStats } from '../lib/transcript'
import { hasStudentProfile, useStudentProfileQuery } from '../lib/studentProfileQuery'

export function TranscriptPage() {
  const { t, locale } = useTranslation()
  const queryClient = useQueryClient()
  const profileQuery = useStudentProfileQuery()
  const transcriptQuery = useTranscriptRecords()
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const progressQuery = useQuery({
    queryKey: ['progress'],
    queryFn: progressApi.get,
    enabled: Boolean(profileQuery.data?.profile?.degreeId),
    retry: false,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => transcriptApi.remove(id),
    onMutate: (id) => setDeletingId(id),
    onSettled: () => setDeletingId(null),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TRANSCRIPT_QUERY_KEY })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
    },
  })

  const records = transcriptQuery.data?.completedCourses ?? []
  const stats = useMemo(() => computeTranscriptStats(records), [records])
  const completionPercent = progressQuery.data?.graduationProgress?.completionPercentage ?? null
  const profile = profileQuery.data?.profile
  const currentSemesterCode = profile?.currentSemesterCode ?? defaultSemesterCode()
  const existingSemesterCodes = useMemo(
    () => [...new Set(records.map((record) => record.semesterCode))],
    [records],
  )
  const hasReadOnlyEntries = stats.readOnlyCount > 0

  if (transcriptQuery.isLoading) {
    return <TranscriptPageSkeleton />
  }

  if (transcriptQuery.isError) {
    return (
      <div className="animate-fade-in">
        <PageHeader title={t('transcript.title')} description={t('transcript.description')} />
        <EmptyState title={t('transcript.loadFailed')} />
      </div>
    )
  }

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title={t('transcript.title')}
        description={t('transcript.description')}
        action={
          hasStudentProfile(profileQuery.data) ? (
            <Link
              to="/progress"
              className="inline-flex items-center gap-2 rounded-xl border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium transition hover:bg-[var(--color-surface-muted)]"
            >
              <GraduationCap className="h-4 w-4" />
              {t('transcript.viewProgress')}
            </Link>
          ) : null
        }
      />

      <TranscriptSummaryCard
        stats={stats}
        completionPercent={completionPercent}
        locale={locale}
        t={t}
      />

      {hasReadOnlyEntries ? (
        <Card className="border-[var(--color-primary)]/15 bg-[var(--color-primary)]/5">
          <div className="flex gap-3">
            <Info className="mt-0.5 h-5 w-5 shrink-0 text-[var(--color-primary)]" />
            <p className="text-sm text-[var(--color-text-muted)]">{t('transcript.officialNotice')}</p>
          </div>
        </Card>
      ) : null}

      <TranscriptAddCourseForm
        defaultSemesterCode={currentSemesterCode}
        catalogYear={profile?.catalogYear}
        currentSemesterCode={currentSemesterCode}
        existingSemesterCodes={existingSemesterCodes}
        locale={locale}
        t={t}
      />

      {records.length === 0 ? (
        <EmptyState
          title={t('transcript.emptyTitle')}
          description={t('transcript.emptyDescription')}
          action={
            <Link
              to="/catalog"
              className="inline-flex items-center gap-2 rounded-xl bg-[var(--color-primary)] px-4 py-2 text-sm font-medium text-white"
            >
              {t('transcript.emptyBrowseCatalog')}
            </Link>
          }
        />
      ) : (
        <TranscriptCourseList
          records={records}
          locale={locale}
          t={t}
          deletingId={deletingId}
          onDelete={(id) => deleteMutation.mutate(id)}
        />
      )}
    </div>
  )
}
