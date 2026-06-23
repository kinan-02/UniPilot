import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TranscriptAddCourseForm } from './TranscriptAddCourseForm'
import { TRANSCRIPT_QUERY_KEY } from '../../hooks/useTranscriptRecords'
import * as endpoints from '../../api/endpoints'
import { I18nProvider } from '../../i18n'

vi.mock('../../hooks/useCatalogCourses', () => ({
  useCatalogCourses: () => ({
    items: [
      {
        id: '665f2b0f2a3f7b2a1a9a7d01',
        courseNumber: '00940411',
        title: 'Intro to Data Science',
        credits: 3.5,
      },
    ],
    isLoading: false,
    isFetching: false,
    hasNextPage: false,
    fetchNextPage: vi.fn(),
  }),
  CATALOG_PAGE_SIZE: 30,
}))

vi.mock('../../api/endpoints', () => ({
  transcriptApi: {
    create: vi.fn(),
  },
  catalogApi: {
    courses: vi.fn(),
  },
}))

describe('TranscriptAddCourseForm progress integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.catalogApi.courses).mockResolvedValue({
      items: [
        {
          id: '665f2b0f2a3f7b2a1a9a7d01',
          courseNumber: '00940411',
          title: 'Intro to Data Science',
          credits: 3.5,
        },
      ],
      total: 1,
      limit: 30,
      offset: 0,
    })
    vi.mocked(endpoints.transcriptApi.create).mockResolvedValue({
      completedCourse: {
        id: 'new-record',
        courseId: '665f2b0f2a3f7b2a1a9a7d01',
        courseNumber: '00940411',
        semesterCode: '2020-2',
        grade: '85',
        creditsEarned: 3.5,
        attempt: 1,
        source: 'manual',
      },
    })
  })

  it('invalidates transcript and graduation progress after a successful add', async () => {
    const user = userEvent.setup()
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    render(
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <TranscriptAddCourseForm
            defaultSemesterCode="2025-1"
            catalogYear={2025}
            currentSemesterCode="2025-1"
            existingSemesterCodes={['2020-2']}
            locale="en"
            t={(key) => key}
          />
        </QueryClientProvider>
      </I18nProvider>,
    )

    await user.type(screen.getByTestId('transcript-course-search'), '00940411')
    await waitFor(
      () => {
        expect(screen.getByText('Intro to Data Science')).toBeInTheDocument()
      },
      { timeout: 2000 },
    )
    await user.click(screen.getByTestId('transcript-add-button'))

    await waitFor(() => {
      expect(endpoints.transcriptApi.create).toHaveBeenCalled()
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: TRANSCRIPT_QUERY_KEY })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['progress'] })
  })
})
