import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Check, Search } from 'lucide-react'
import { catalogApi, transcriptApi } from '../../api/endpoints'
import { TRANSCRIPT_QUERY_KEY } from '../../hooks/useTranscriptRecords'
import { useCatalogCourses } from '../../hooks/useCatalogCourses'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { TranscriptSemesterPicker } from './TranscriptSemesterPicker'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Input } from '../ui/Input'
import { validateSemesterCode } from '../../lib/validation'
import { cn, formatCredits } from '../../lib/utils'
import type { CourseSummary } from '../../types/api'
import type { Locale } from '../../i18n/types'

type TranscriptAddCourseFormProps = {
  defaultSemesterCode: string
  catalogYear?: number | null
  currentSemesterCode?: string | null
  existingSemesterCodes?: string[]
  locale: Locale
  t: (key: string) => string
}

function localizedCourseTitle(course: CourseSummary, locale: Locale): string {
  if (locale === 'he' && course.titleHebrew) return course.titleHebrew
  return course.title ?? course.titleHebrew ?? course.courseNumber
}

export function TranscriptAddCourseForm({
  defaultSemesterCode,
  catalogYear,
  currentSemesterCode,
  existingSemesterCodes = [],
  locale,
  t,
}: TranscriptAddCourseFormProps) {
  const queryClient = useQueryClient()
  const searchRef = useRef<HTMLInputElement>(null)
  const semesterInitializedRef = useRef(false)
  const [query, setQuery] = useState('')
  const [selectedCourse, setSelectedCourse] = useState<CourseSummary | null>(null)
  const [semesterCode, setSemesterCode] = useState(defaultSemesterCode)
  const [grade, setGrade] = useState('85')
  const [creditsEarned, setCreditsEarned] = useState('3')
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [semesterError, setSemesterError] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)

  const debouncedQuery = useDebouncedValue(query.trim(), 300)
  const coursesQuery = useCatalogCourses({
    query: debouncedQuery,
    faculty: '',
  })

  useEffect(() => {
    if (semesterInitializedRef.current) return
    setSemesterCode(defaultSemesterCode)
    semesterInitializedRef.current = true
  }, [defaultSemesterCode])

  useEffect(() => {
    if (!selectedCourse) return
    if (selectedCourse.credits != null) {
      setCreditsEarned(String(selectedCourse.credits))
    }
  }, [selectedCourse])

  useEffect(() => {
    if (!debouncedQuery || selectedCourse) return
    if (!/^0\d{7}$/.test(debouncedQuery)) return
    const exact = coursesQuery.items.find((course) => course.courseNumber === debouncedQuery)
    if (exact) setSelectedCourse(exact)
  }, [coursesQuery.items, debouncedQuery, selectedCourse])

  const suggestions = useMemo(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) return []
    return coursesQuery.items.slice(0, 8)
  }, [coursesQuery.items, debouncedQuery])

  const addMutation = useMutation({
    mutationFn: async () => {
      let course = selectedCourse
      if (!course?.id) {
        const trimmed = query.trim()
        if (!trimmed) {
          throw new Error(t('transcript.courseRequired'))
        }
        const courseResponse = await catalogApi.courses({
          courseNumber: trimmed,
          limit: 1,
          offset: 0,
        })
        course = courseResponse.items[0]
        if (!course?.id) {
          throw new Error(t('transcript.courseNotFound'))
        }
      }
      const semesterResult = validateSemesterCode(semesterCode)
      if (!semesterResult.ok) {
        throw new Error(t(semesterResult.message))
      }
      return transcriptApi.create({
        courseId: course.id,
        semesterCode,
        grade: Number(grade),
        creditsEarned: Number(creditsEarned),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: TRANSCRIPT_QUERY_KEY })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
      setQuery('')
      setSelectedCourse(null)
      setError('')
      setSuccess(t('transcript.added'))
      window.setTimeout(() => setSuccess(''), 3000)
      searchRef.current?.focus()
    },
    onError: (err: Error) => {
      setSuccess('')
      setError(err.message || t('transcript.addFailed'))
    },
  })

  return (
    <Card data-testid="transcript-add-form">
      <div className="mb-5">
        <h2 className="text-sm font-semibold">{t('transcript.addCourse')}</h2>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">{t('transcript.addCourseHint')}</p>
      </div>

      <form
        className="space-y-5"
        onSubmit={(event) => {
          event.preventDefault()
          setSemesterError('')
          const semesterResult = validateSemesterCode(semesterCode)
          if (!semesterResult.ok) {
            setSemesterError(t(semesterResult.message))
            return
          }
          addMutation.mutate()
        }}
      >
        <div className="relative">
          <label className="mb-1.5 block text-sm font-medium" htmlFor="transcript-course-search">
            {t('transcript.courseSearch')}
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute start-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--color-text-muted)]" />
            <input
              ref={searchRef}
              id="transcript-course-search"
              type="search"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value)
                setSelectedCourse(null)
                setError('')
                setMenuOpen(true)
              }}
              onFocus={() => setMenuOpen(true)}
              placeholder={t('transcript.courseSearchPlaceholder')}
              className={cn(
                'h-11 w-full rounded-xl border border-[var(--color-border)] bg-white ps-10 pe-10 text-sm',
                'focus:border-[var(--color-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/15',
              )}
              data-testid="transcript-course-search"
            />
            {selectedCourse ? (
              <Check
                className="absolute end-3 top-1/2 h-4 w-4 -translate-y-1/2 text-emerald-600"
                aria-hidden
              />
            ) : null}
          </div>

          {menuOpen && suggestions.length > 0 && !selectedCourse ? (
            <div className="absolute z-20 mt-2 w-full overflow-hidden rounded-xl border border-[var(--color-border)] bg-white shadow-[var(--shadow-soft)]">
              {suggestions.map((course) => (
                <button
                  key={course.courseNumber}
                  type="button"
                  className="flex w-full items-start justify-between gap-3 px-4 py-3 text-start text-sm hover:bg-[var(--color-surface-muted)]"
                  onClick={() => {
                    setSelectedCourse(course)
                    setQuery(course.courseNumber)
                    setMenuOpen(false)
                    setError('')
                  }}
                >
                  <span>
                    <span className="font-mono font-medium text-[var(--color-primary)]">
                      {course.courseNumber}
                    </span>
                    <span className="mt-0.5 block text-[var(--color-text)]">
                      {localizedCourseTitle(course, locale)}
                    </span>
                  </span>
                  {course.credits != null ? (
                    <span className="shrink-0 text-xs text-[var(--color-text-muted)]">
                      {formatCredits(course.credits)} {t('common.credits')}
                    </span>
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}

          {selectedCourse ? (
            <div className="mt-3 rounded-xl border border-[var(--color-primary)]/15 bg-[var(--color-primary)]/5 px-4 py-3">
              <p className="font-mono text-sm font-medium text-[var(--color-primary)]">
                {selectedCourse.courseNumber}
              </p>
              <p className="mt-1 text-sm">{localizedCourseTitle(selectedCourse, locale)}</p>
            </div>
          ) : null}
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(260px,320px)_repeat(2,minmax(0,1fr))] lg:items-start">
          <TranscriptSemesterPicker
            value={semesterCode}
            onChange={(value) => {
              setSemesterCode(value)
              setSemesterError('')
            }}
            catalogYear={catalogYear}
            currentSemesterCode={currentSemesterCode}
            existingSemesterCodes={existingSemesterCodes}
            error={semesterError}
          />
          <Input
            label={t('transcript.grade')}
            type="number"
            min={0}
            max={100}
            value={grade}
            onChange={(event) => setGrade(event.target.value)}
            required
          />
          <Input
            label={t('transcript.creditsEarned')}
            type="number"
            step="0.5"
            min={0}
            value={creditsEarned}
            onChange={(event) => setCreditsEarned(event.target.value)}
            required
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" loading={addMutation.isPending} data-testid="transcript-add-button">
            {t('transcript.addButton')}
          </Button>
          {success ? <p className="text-sm text-emerald-700">{success}</p> : null}
          {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
        </div>
      </form>
    </Card>
  )
}
