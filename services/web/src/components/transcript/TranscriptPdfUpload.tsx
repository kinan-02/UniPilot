import { useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FileUp,
  Search,
  Upload,
  User,
  X,
} from 'lucide-react'
import { transcriptImportApi } from '../../api/endpoints'
import { useTranscriptPreviewCatalog } from '../../hooks/useTranscriptPreviewCatalog'
import { TRANSCRIPT_QUERY_KEY } from '../../hooks/useTranscriptRecords'
import { compareSemesterCodesDesc, gradeBadgeTone } from '../../lib/transcript'
import {
  displayTitleForParsedCourse,
  localizeParseWarning,
  previewCourseSearchHaystack,
} from '../../lib/transcriptImportDisplay'
import { semesterLabel } from '../../lib/semester'
import { cn, formatCredits } from '../../lib/utils'
import type { Locale } from '../../i18n/types'
import type { CourseSummary, ParsedTranscriptCourse, TranscriptParsePreview } from '../../types/api'
import { Badge } from '../ui/Card'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

type TranscriptPdfUploadProps = {
  locale: Locale
  t: (key: string, params?: Record<string, string | number>) => string
  featured?: boolean
}

function rowKey(course: ParsedTranscriptCourse) {
  return `${course.courseNumber}:${course.semesterCode}:${course.attempt ?? 1}:${course.grade}`
}

function groupPreviewBySemester(courses: ParsedTranscriptCourse[]) {
  const groups = new Map<string, ParsedTranscriptCourse[]>()
  for (const course of courses) {
    const existing = groups.get(course.semesterCode) ?? []
    existing.push(course)
    groups.set(course.semesterCode, existing)
  }
  return [...groups.entries()]
    .map(([semesterCode, semesterCourses]) => ({
      semesterCode,
      courses: [...semesterCourses].sort((left, right) =>
        left.courseNumber.localeCompare(right.courseNumber),
      ),
    }))
    .sort((left, right) => compareSemesterCodesDesc(left.semesterCode, right.semesterCode))
}

const EMPTY_CATALOG_MAP = new Map<string, CourseSummary>()

export function TranscriptPdfUpload({ locale, t, featured = false }: TranscriptPdfUploadProps) {
  const queryClient = useQueryClient()
  const inputRef = useRef<HTMLInputElement>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<TranscriptParsePreview | null>(null)
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [previewFilter, setPreviewFilter] = useState('')
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const catalogQuery = useTranscriptPreviewCatalog(preview)
  const catalogByNumber = catalogQuery.data ?? EMPTY_CATALOG_MAP

  const selectedCourses = useMemo(() => {
    if (!preview) return []
    return preview.courses.filter((course) => selectedKeys.has(rowKey(course)))
  }, [preview, selectedKeys])

  const filteredPreviewCourses = useMemo(() => {
    if (!preview) return []
    const query = previewFilter.trim().toLowerCase()
    if (!query) return preview.courses
    return preview.courses.filter((course) => {
      const displayTitle = displayTitleForParsedCourse(course, catalogByNumber, locale)
      return previewCourseSearchHaystack(course, displayTitle).includes(query)
    })
  }, [preview, previewFilter, catalogByNumber, locale])

  const previewGroups = useMemo(
    () => groupPreviewBySemester(filteredPreviewCourses),
    [filteredPreviewCourses],
  )

  const resetPreview = () => {
    setPreview(null)
    setSelectedKeys(new Set())
    setPreviewFilter('')
  }

  const applyFile = (file: File | null) => {
    setSelectedFile(file)
    resetPreview()
    setError('')
    setSuccess('')
  }

  const parseMutation = useMutation({
    mutationFn: (file: File) => transcriptImportApi.parse(file),
    onSuccess: (data) => {
      setPreview(data.parsePreview)
      setSelectedKeys(new Set(data.parsePreview.courses.map(rowKey)))
      setPreviewFilter('')
      setError('')
      setSuccess('')
    },
    onError: (err: Error) => {
      resetPreview()
      setSuccess('')
      setError(err.message || t('transcript.upload.parseFailed'))
    },
  })

  const commitMutation = useMutation({
    mutationFn: () => transcriptImportApi.commit(selectedCourses),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: TRANSCRIPT_QUERY_KEY })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
      queryClient.invalidateQueries({ queryKey: ['curriculum-graph'] })
      const { createdCount, skippedCount, unresolvedCount } = data.importResult
      setSuccess(
        t('transcript.upload.importSuccess', {
          created: createdCount,
          skipped: skippedCount,
          unresolved: unresolvedCount,
        }),
      )
      resetPreview()
      setSelectedFile(null)
      setError('')
      if (inputRef.current) inputRef.current.value = ''
    },
    onError: (err: Error) => {
      setSuccess('')
      setError(err.message || t('transcript.upload.importFailed'))
    },
  })

  const toggleCourse = (course: ParsedTranscriptCourse) => {
    const key = rowKey(course)
    setSelectedKeys((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const toggleSemester = (courses: ParsedTranscriptCourse[], select: boolean) => {
    setSelectedKeys((current) => {
      const next = new Set(current)
      for (const course of courses) {
        const key = rowKey(course)
        if (select) next.add(key)
        else next.delete(key)
      }
      return next
    })
  }

  const selectAllVisible = () => {
    setSelectedKeys(new Set(filteredPreviewCourses.map(rowKey)))
  }

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file?.type === 'application/pdf' || file?.name.toLowerCase().endsWith('.pdf')) {
      applyFile(file)
    } else {
      setError(t('transcript.upload.invalidFile'))
    }
  }

  return (
    <Card
      data-testid="transcript-upload-form"
      className={cn(
        featured && 'border-[var(--color-primary)]/25 bg-gradient-to-br from-white to-[var(--color-primary)]/5',
      )}
    >
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--color-primary)]/10 text-[var(--color-primary)]">
              <FileText className="h-4 w-4" aria-hidden />
            </div>
            <h2 className="text-sm font-semibold">{t('transcript.upload.title')}</h2>
          </div>
          <p className="mt-2 max-w-2xl text-sm text-[var(--color-text-muted)]">
            {featured ? t('transcript.upload.featuredHint') : t('transcript.upload.hint')}
          </p>
        </div>
        {preview ? (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              resetPreview()
              setSelectedFile(null)
              if (inputRef.current) inputRef.current.value = ''
            }}
            data-testid="transcript-upload-clear"
          >
            <X className="h-4 w-4" />
            {t('transcript.upload.clearPreview')}
          </Button>
        ) : null}
      </div>

      <div className="space-y-4">
        {!preview ? (
          <div
            data-testid="transcript-upload-dropzone"
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={cn(
              'rounded-xl border-2 border-dashed px-5 py-8 text-center transition-colors',
              dragging
                ? 'border-[var(--color-primary)] bg-[var(--color-primary)]/5'
                : 'border-[var(--color-border)] bg-[var(--color-surface-muted)]/40',
            )}
          >
            <input
              ref={inputRef}
              data-testid="transcript-upload-input"
              type="file"
              accept="application/pdf,.pdf"
              className="hidden"
              onChange={(event) => applyFile(event.target.files?.[0] ?? null)}
            />
            <div className="mx-auto flex max-w-md flex-col items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white shadow-sm">
                <Upload className="h-5 w-5 text-[var(--color-primary)]" aria-hidden />
              </div>
              <div>
                <p className="text-sm font-medium text-[var(--color-text)]">
                  {dragging ? t('transcript.upload.dropActive') : t('transcript.upload.dropHint')}
                </p>
                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                  {t('transcript.upload.supportedFormats')}
                </p>
              </div>
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => inputRef.current?.click()}
                  data-testid="transcript-upload-choose"
                >
                  <FileUp className="h-4 w-4" />
                  {t('transcript.upload.chooseFile')}
                </Button>
                {selectedFile ? (
                  <span
                    className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs text-[var(--color-text-muted)]"
                    data-testid="transcript-upload-filename"
                  >
                    <FileText className="h-3.5 w-3.5" />
                    {selectedFile.name}
                  </span>
                ) : null}
              </div>
              {selectedFile ? (
                <Button
                  type="button"
                  disabled={parseMutation.isPending}
                  loading={parseMutation.isPending}
                  onClick={() => parseMutation.mutate(selectedFile)}
                  data-testid="transcript-upload-parse"
                >
                  {parseMutation.isPending
                    ? t('transcript.upload.parsing')
                    : t('transcript.upload.parseButton')}
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}

        {preview ? (
          <div className="space-y-4" data-testid="transcript-upload-preview">
            <div className="grid gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-muted)]/30 p-4 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t('transcript.upload.previewCount', { count: preview.courses.length })}
                </p>
                <p className="mt-1 text-lg font-semibold tabular-nums">
                  {t('transcript.upload.selectedCount', { count: selectedCourses.length })}
                </p>
              </div>
              {preview.studentName || preview.studentId ? (
                <div className="flex items-start gap-2 sm:col-span-2">
                  <User className="mt-0.5 h-4 w-4 shrink-0 text-[var(--color-text-muted)]" aria-hidden />
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                      {t('transcript.upload.studentInfo')}
                    </p>
                    <p className="mt-1 text-sm font-medium">
                      {preview.studentName ?? '—'}
                      {preview.studentId ? (
                        <span className="ms-2 font-mono text-xs text-[var(--color-text-muted)]">
                          {preview.studentId}
                        </span>
                      ) : null}
                    </p>
                  </div>
                </div>
              ) : null}
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-text-muted)]">
                  {t('transcript.upload.metadataPages')}
                </p>
                <p className="mt-1 text-sm tabular-nums">
                  {preview.parseMetadata.pageCount} · {preview.parseMetadata.pipelineVersion}
                </p>
              </div>
            </div>

            {preview.warnings.length ? (
              <div
                className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
                data-testid="transcript-upload-warnings"
              >
                {preview.warnings.map((warning) => (
                  <p key={warning} className="flex items-start gap-2">
                    <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
                    {localizeParseWarning(warning, t)}
                  </p>
                ))}
              </div>
            ) : null}

            <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div className="relative flex-1 lg:max-w-sm">
                <Search
                  className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]"
                  aria-hidden
                />
                <input
                  type="search"
                  value={previewFilter}
                  onChange={(event) => setPreviewFilter(event.target.value)}
                  placeholder={t('transcript.upload.filterPreview')}
                  className="h-10 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-3 text-sm focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15"
                  data-testid="transcript-upload-filter"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="ghost" size="sm" onClick={selectAllVisible}>
                  {t('transcript.upload.selectAll')}
                </Button>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedKeys(new Set())}
                >
                  {t('transcript.upload.deselectAll')}
                </Button>
              </div>
            </div>

            {preview.courses.length === 0 ? (
              <p className="text-sm text-[var(--color-text-muted)]">{t('transcript.upload.noCourses')}</p>
            ) : previewGroups.length === 0 ? (
              <Card className="border-dashed text-center text-sm text-[var(--color-text-muted)]">
                {t('common.noResults')}
              </Card>
            ) : (
              <div className="space-y-3">
                {previewGroups.map((group) => {
                  const groupKeys = group.courses.map(rowKey)
                  const selectedInGroup = groupKeys.filter((key) => selectedKeys.has(key)).length
                  const allSelected = selectedInGroup === group.courses.length

                  return (
                    <Card key={group.semesterCode} className="overflow-hidden p-0">
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-border)] bg-[var(--color-surface-muted)]/50 px-4 py-3">
                        <label className="flex cursor-pointer items-center gap-3">
                          <input
                            type="checkbox"
                            checked={allSelected && group.courses.length > 0}
                            ref={(element) => {
                              if (element) {
                                element.indeterminate =
                                  selectedInGroup > 0 && selectedInGroup < group.courses.length
                              }
                            }}
                            onChange={() => toggleSemester(group.courses, !allSelected)}
                            aria-label={semesterLabel(group.semesterCode, locale)}
                          />
                          <div>
                            <p className="text-sm font-medium">
                              {semesterLabel(group.semesterCode, locale)}
                            </p>
                            <p className="text-xs text-[var(--color-text-muted)]">
                              {group.semesterCode} · {group.courses.length}{' '}
                              {t('transcript.courses').toLowerCase()}
                            </p>
                          </div>
                        </label>
                        <p className="text-xs tabular-nums text-[var(--color-text-muted)]">
                          {selectedInGroup}/{group.courses.length}
                        </p>
                      </div>
                      <div className="divide-y divide-[var(--color-border)]">
                        {group.courses.map((course) => {
                          const key = rowKey(course)
                          const lowConfidence = course.confidence < 0.7
                          const displayTitle = displayTitleForParsedCourse(course, catalogByNumber, locale)
                          const localizedWarnings = course.warnings.map((warning) =>
                            localizeParseWarning(warning, t),
                          )
                          return (
                            <label
                              key={key}
                              className={cn(
                                'flex cursor-pointer gap-3 px-4 py-3 transition hover:bg-[var(--color-surface-muted)]/30',
                                selectedKeys.has(key) && 'bg-[var(--color-primary)]/[0.03]',
                                lowConfidence && 'border-s-2 border-s-amber-400',
                              )}
                              data-testid={`transcript-preview-row-${course.courseNumber}`}
                            >
                              <input
                                type="checkbox"
                                checked={selectedKeys.has(key)}
                                onChange={() => toggleCourse(course)}
                                className="mt-1"
                              />
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-mono text-sm font-medium text-[var(--color-primary)]">
                                    {course.courseNumber}
                                  </span>
                                  <Badge tone={gradeBadgeTone(course.grade)}>
                                    {t('transcript.gradeLabel').replace('{grade}', String(course.grade))}
                                  </Badge>
                                  {lowConfidence ? (
                                    <Badge tone="warning">{t('transcript.upload.lowConfidence')}</Badge>
                                  ) : null}
                                </div>
                                {displayTitle ? (
                                  <p className="mt-1 text-sm text-[var(--color-text)]">{displayTitle}</p>
                                ) : null}
                                <p className="mt-1 text-xs text-[var(--color-text-muted)]">
                                  {formatCredits(course.creditsEarned)} {t('common.credits')}
                                  {localizedWarnings.length
                                    ? ` · ${localizedWarnings.join('; ')}`
                                    : null}
                                </p>
                              </div>
                            </label>
                          )
                        })}
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}

            <div className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--color-border)] bg-white/95 p-4 shadow-[var(--shadow-soft)] backdrop-blur-sm">
              <p className="text-sm text-[var(--color-text-muted)]">
                {t('transcript.upload.selectedCount', { count: selectedCourses.length })}
              </p>
              <Button
                type="button"
                disabled={selectedCourses.length === 0 || commitMutation.isPending}
                loading={commitMutation.isPending}
                onClick={() => commitMutation.mutate()}
                data-testid="transcript-upload-commit"
              >
                {commitMutation.isPending
                  ? t('transcript.upload.importing')
                  : t('transcript.upload.importButton', { count: selectedCourses.length })}
              </Button>
            </div>
          </div>
        ) : null}

        {error ? (
          <div
            className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
            role="alert"
            data-testid="transcript-upload-error"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {error}
          </div>
        ) : null}
        {success ? (
          <div
            className="flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900"
            role="status"
            data-testid="transcript-upload-success"
          >
            <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            {success}
          </div>
        ) : null}
      </div>
    </Card>
  )
}
