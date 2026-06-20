import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { catalogApi, transcriptApi } from '../api/endpoints'
import { Button } from '../components/ui/Button'
import { Badge, Card, EmptyState, PageHeader, Spinner } from '../components/ui/Card'
import { Input } from '../components/ui/Input'
import { formatCredits } from '../lib/utils'

export function TranscriptPage() {
  const queryClient = useQueryClient()
  const [courseNumber, setCourseNumber] = useState('')
  const [semesterCode, setSemesterCode] = useState('2025-1')
  const [grade, setGrade] = useState('85')
  const [creditsEarned, setCreditsEarned] = useState('3')
  const [error, setError] = useState('')

  const transcriptQuery = useQuery({
    queryKey: ['transcript'],
    queryFn: transcriptApi.list,
  })

  const addMutation = useMutation({
    mutationFn: async () => {
      const courseResponse = await catalogApi.courses({
        courseNumber: courseNumber.trim(),
        limit: 1,
        offset: 0,
      })
      const course = courseResponse.items[0]
      if (!course?.id) {
        throw new Error('Course not found in catalog')
      }
      return transcriptApi.create({
        courseId: course.id,
        semesterCode,
        grade: Number(grade),
        creditsEarned: Number(creditsEarned),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript'] })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
      setError('')
      setCourseNumber('')
    },
    onError: (err: Error) => setError(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => transcriptApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['transcript'] })
      queryClient.invalidateQueries({ queryKey: ['progress'] })
    },
  })

  const records = transcriptQuery.data?.completedCourses ?? []

  return (
    <div className="animate-fade-in space-y-6">
      <PageHeader
        title="Transcript"
        description="Track completed courses manually. Official registrar imports are read-only."
      />

      <Card>
        <h2 className="mb-4 text-sm font-semibold">Add completed course</h2>
        <form
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault()
            addMutation.mutate()
          }}
        >
          <Input
            label="Course number"
            placeholder="00940345"
            value={courseNumber}
            onChange={(e) => setCourseNumber(e.target.value)}
            required
          />
          <Input
            label="Semester"
            placeholder="2025-1"
            value={semesterCode}
            onChange={(e) => setSemesterCode(e.target.value)}
            required
          />
          <Input
            label="Grade"
            type="number"
            min={0}
            max={100}
            value={grade}
            onChange={(e) => setGrade(e.target.value)}
            required
          />
          <Input
            label="Credits earned"
            type="number"
            step="0.5"
            min={0}
            value={creditsEarned}
            onChange={(e) => setCreditsEarned(e.target.value)}
            required
          />
          <div className="sm:col-span-2 lg:col-span-4 flex items-center gap-4">
            <Button type="submit" loading={addMutation.isPending}>
              Add course
            </Button>
            {error ? <p className="text-sm text-[var(--color-danger)]">{error}</p> : null}
          </div>
        </form>
      </Card>

      {transcriptQuery.isLoading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : records.length ? (
        <div className="overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-white">
          <div className="divide-y divide-[var(--color-border)]">
            {records.map((record) => (
              <div
                key={record.id}
                className="flex items-center justify-between gap-4 px-5 py-4"
              >
                <div>
                  <p className="font-mono text-sm font-medium text-[var(--color-primary)]">
                    {record.courseNumber ?? record.courseId}
                  </p>
                  <p className="text-sm">{record.courseTitle ?? 'Course'}</p>
                  <p className="text-xs text-[var(--color-text-muted)]">
                    {record.semesterCode} · Grade {record.grade} ·{' '}
                    {formatCredits(record.creditsEarned)} cr
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone="neutral">{record.source}</Badge>
                  {record.source === 'manual' ? (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => deleteMutation.mutate(record.id)}
                      aria-label="Delete course"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <EmptyState
          title="No completed courses yet"
          description="Add courses you've finished to unlock accurate graduation progress."
        />
      )}
    </div>
  )
}
