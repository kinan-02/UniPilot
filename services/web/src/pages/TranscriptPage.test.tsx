import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { TranscriptPage } from './TranscriptPage'
import * as endpoints from '../api/endpoints'
import { I18nProvider } from '../i18n'

vi.mock('../hooks/useCatalogCourses', () => ({
  useCatalogCourses: () => ({
    items: [
      {
        id: '665f2b0f2a3f7b2a1a9a7d01',
        courseNumber: '00940345',
        title: 'Discrete Mathematics',
        credits: 5,
      },
    ],
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

const sampleRecords = [
  {
    id: 'record-1',
    courseId: '665f2b0f2a3f7b2a1a9a7d01',
    courseNumber: '00940345',
    courseTitle: 'Discrete Mathematics',
    semesterCode: '2024-2',
    grade: '88',
    creditsEarned: 5,
    attempt: 1,
    source: 'manual',
  },
  {
    id: 'record-2',
    courseId: '665f2b0f2a3f7b2a1a9a7d02',
    courseNumber: '00940411',
    courseTitle: 'Algorithms',
    semesterCode: '2025-1',
    grade: '72',
    creditsEarned: 3.5,
    attempt: 1,
    source: 'official',
  },
]

function renderTranscript(locale: 'en' | 'he' = 'en') {
  localStorage.setItem('unipilot_locale', locale)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <TranscriptPage />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>,
  )
}

describe('TranscriptPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.mocked(endpoints.transcriptApi.listAll).mockResolvedValue({
      completedCourses: sampleRecords,
      pagination: { total: 2, page: 1, limit: 2 },
    })
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: {
        completionPercentage: 12,
        completedCredits: 8.5,
        totalRequiredCredits: 155,
        creditsRemaining: 146.5,
        statusSummary: 'in_progress',
        requirementProgress: [],
      },
    } as never)
  })

  it('renders localized header, summary, and semester groups', async () => {
    renderTranscript()

    expect(await screen.findByRole('heading', { level: 1, name: 'Transcript' })).toBeInTheDocument()
    expect(screen.getByTestId('transcript-summary-card')).toBeInTheDocument()
    expect(screen.getByTestId('transcript-course-list')).toBeInTheDocument()
    expect(screen.getByTestId('transcript-row-00940411')).toBeInTheDocument()
    expect(screen.getByText('Discrete Mathematics')).toBeInTheDocument()
    expect(await screen.findByTestId('transcript-semester-picker')).toBeInTheDocument()
  })

  it('shows official notice for read-only entries', async () => {
    renderTranscript()
    expect(await screen.findByText(/imported from the registrar/i)).toBeInTheDocument()
    expect(screen.getByText('Official')).toBeInTheDocument()
  })

  it('filters transcript rows', async () => {
    const user = userEvent.setup()
    renderTranscript()
    await screen.findByTestId('transcript-course-list')

    await user.type(screen.getByTestId('transcript-filter-input'), 'algorithms')
    expect(screen.getByText('Algorithms')).toBeInTheDocument()
    expect(screen.queryByText('Discrete Mathematics')).not.toBeInTheDocument()
  })

  it('renders empty state when no records exist', async () => {
    vi.mocked(endpoints.transcriptApi.listAll).mockResolvedValue({
      completedCourses: [],
      pagination: { total: 0, page: 1, limit: 0 },
    })
    renderTranscript()

    expect(await screen.findByText(/no completed courses yet/i)).toBeInTheDocument()
    expect(screen.queryByTestId('transcript-summary-card')).not.toBeInTheDocument()
  })
})
