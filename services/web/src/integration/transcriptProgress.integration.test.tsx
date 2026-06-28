import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProgressPage } from '../pages/ProgressPage'
import { TranscriptPage } from '../pages/TranscriptPage'
import * as endpoints from '../api/endpoints'
import {
  baseGraduationProgress,
  emptyCurriculumGraph,
  electivePool,
  generalTechnionPools,
  PROGRAM_CODE,
} from '../testFixtures/progress'
import { buildTranscriptCourseNumbers } from '../lib/electivePools'
import { I18nProvider } from '../i18n'

vi.mock('../hooks/useCatalogCourses', () => ({
  useCatalogCourses: () => ({
    items: [],
    isLoading: false,
    isFetching: false,
    hasNextPage: false,
    fetchNextPage: vi.fn(),
  }),
  CATALOG_PAGE_SIZE: 30,
}))

vi.mock('../api/endpoints', () => ({
  transcriptApi: {
    listAll: vi.fn(),
    create: vi.fn(),
    remove: vi.fn(),
  },
  transcriptImportApi: {
    parse: vi.fn(),
    commit: vi.fn(),
  },
  progressApi: {
    get: vi.fn(),
    curriculumGraph: vi.fn(),
  },
  catalogApi: {
    courses: vi.fn(),
  },
  profileApi: {
    get: vi.fn(),
  },
}))

vi.mock('../lib/studentProfileQuery', async () => {
  const actual = await vi.importActual<typeof import('../lib/studentProfileQuery')>(
    '../lib/studentProfileQuery',
  )
  return {
    ...actual,
    useStudentProfileQuery: () => ({
      data: {
        profile: {
          id: 'profile-1',
          userId: 'user-1',
          institutionId: 'technion',
          programType: 'BSc',
          degreeId: 'degree-1',
          catalogYear: 2025,
          currentSemesterCode: '2025-1',
        },
      },
      isLoading: false,
      isError: false,
    }),
  }
})

const dsPool = electivePool({
  groupId: `${PROGRAM_CODE}:elective-ds-pool`,
  courses: [
    { courseNumber: '00940411', title: 'Intro to Data Science', credits: 3.5 },
    { courseNumber: '00940345', title: 'Discrete Math', credits: 4 },
  ],
  courseCount: 2,
})

const progressWithDsCourse = baseGraduationProgress({
  completedCredits: 3.5,
  completionPercentage: 2.26,
  statusSummary: 'in_progress',
  requirementProgress: [
    {
      requirementGroupId: `${PROGRAM_CODE}:elective-ds`,
      title: 'DS electives',
      isMandatory: false,
      status: 'in_progress',
      minCredits: 24.5,
      creditsCompleted: 3.5,
      creditsRemaining: 21,
      eligibilityEnforcement: 'strict_pool',
      linkedPoolGroupId: `${PROGRAM_CODE}:elective-ds-pool`,
      completedCourses: [
        {
          courseId: 'c-ds',
          courseNumber: '00940411',
          courseTitle: 'Intro to Data Science',
          creditsEarned: 3.5,
        },
      ],
    },
  ],
})

function renderWithClient(ui: React.ReactElement) {
  localStorage.setItem('unipilot_locale', 'en')
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    queryClient,
    ...render(
      <I18nProvider>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>{ui}</MemoryRouter>
        </QueryClientProvider>
      </I18nProvider>,
    ),
  }
}

describe('Transcript ↔ Progress integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.transcriptApi.listAll).mockResolvedValue({
      completedCourses: [],
      pagination: { total: 0, page: 1, limit: 0 },
    })
    vi.mocked(endpoints.progressApi.curriculumGraph).mockResolvedValue({
      curriculumGraph: {
        ...emptyCurriculumGraph(),
        electiveBuckets: [dsPool, ...generalTechnionPools()],
      },
    })
  })

  it('derives transcript course numbers from graduation progress buckets', () => {
    const numbers = buildTranscriptCourseNumbers(progressWithDsCourse.requirementProgress)
    expect(numbers.has('00940411')).toBe(true)
    expect(numbers.has('00940345')).toBe(false)
  })

  it('marks pool courses as counted when they appear in requirementProgress.completedCourses', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: progressWithDsCourse,
    })

    renderWithClient(<ProgressPage />)
    await screen.findByTestId('progress-summary-card')

    const poolCard = await screen.findByTestId(`elective-pool-card-${dsPool.groupId}`)
    await user.click(poolCard.querySelector('button[aria-expanded="false"]')!)

    const detail = await screen.findByTestId(`elective-pool-detail-${dsPool.groupId}`)
    await user.click(screen.getByRole('button', { name: /^counted/i }))
    expect(detail).toHaveTextContent('00940411')
    expect(detail).toHaveTextContent(/counted/i)
  })

  it('invalidates graduation progress after deleting a transcript record', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.transcriptApi.listAll).mockResolvedValue({
      completedCourses: [
        {
          id: 'record-1',
          courseId: 'c-ds',
          courseNumber: '00940411',
          courseTitle: 'Intro to Data Science',
          semesterCode: '2024-2',
          grade: '88',
          creditsEarned: 3.5,
          attempt: 1,
          source: 'manual',
        },
      ],
      pagination: { total: 1, page: 1, limit: 1 },
    })
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: progressWithDsCourse,
    })
    vi.mocked(endpoints.transcriptApi.remove).mockResolvedValue({ deleted: true })

    const { queryClient } = renderWithClient(<TranscriptPage />)
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    await screen.findByTestId('transcript-row-00940411')
    await user.click(screen.getByRole('button', { name: /remove/i }))
    await user.click(screen.getByRole('button', { name: /^remove$/i }))

    await waitFor(() => {
      expect(endpoints.transcriptApi.remove).toHaveBeenCalledWith('record-1')
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['progress'] })
  })

  it('invalidates graduation progress after importing transcript courses', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.transcriptImportApi.parse).mockResolvedValue({
      parsePreview: {
        courses: [
          {
            courseNumber: '00940411',
            semesterCode: '2024-2',
            grade: 88,
            creditsEarned: 3.5,
            attempt: 1,
            title: 'Intro to Data Science',
            confidence: 0.95,
            warnings: [],
          },
        ],
        warnings: [],
        parseMetadata: {
          pageCount: 1,
          extractor: 'pymupdf',
          pipelineVersion: '0.3.0-official-he-en',
          textCharCount: 1000,
          ocrUsed: false,
        },
      },
    })
    vi.mocked(endpoints.transcriptImportApi.commit).mockResolvedValue({
      importResult: {
        created: [],
        skippedDuplicates: [],
        unresolved: [],
        createdCount: 1,
        skippedCount: 0,
        unresolvedCount: 0,
      },
    })
    vi.mocked(endpoints.transcriptApi.listAll).mockResolvedValue({
      completedCourses: [],
      pagination: { total: 0, page: 1, limit: 0 },
    })
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: progressWithDsCourse,
    })

    const { queryClient } = renderWithClient(<TranscriptPage />)
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')

    await screen.findByTestId('transcript-upload-dropzone')
    const file = new File(['pdf'], 'transcript.pdf', { type: 'application/pdf' })
    await user.upload(screen.getByTestId('transcript-upload-input'), file)
    await user.click(screen.getByTestId('transcript-upload-parse'))
    await screen.findByTestId('transcript-upload-preview')
    await user.click(screen.getByTestId('transcript-upload-commit'))

    await waitFor(() => {
      expect(endpoints.transcriptImportApi.commit).toHaveBeenCalled()
    })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['progress'] })
  })

  it('shows updated completion on transcript summary from shared progress query', async () => {
    vi.mocked(endpoints.transcriptApi.listAll).mockResolvedValue({
      completedCourses: [
        {
          id: 'record-1',
          courseId: 'c-ds',
          courseNumber: '00940411',
          courseTitle: 'Intro to Data Science',
          semesterCode: '2024-2',
          grade: '88',
          creditsEarned: 3.5,
          attempt: 1,
          source: 'manual',
        },
      ],
      pagination: { total: 1, page: 1, limit: 1 },
    })
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: progressWithDsCourse,
    })

    renderWithClient(<TranscriptPage />)
    expect(await screen.findByText(/overall completion: 2\.3%/i)).toBeInTheDocument()
  })
})
