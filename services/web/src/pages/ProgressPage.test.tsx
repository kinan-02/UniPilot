import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProgressPage } from './ProgressPage'
import * as endpoints from '../api/endpoints'
import { ApiError } from '../lib/api'
import { I18nProvider } from '../i18n'

vi.mock('../api/endpoints', () => ({
  progressApi: { get: vi.fn(), curriculumGraph: vi.fn() },
}))

function renderProgress(locale: 'en' | 'he' = 'en') {
  localStorage.setItem('unipilot_locale', locale)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <I18nProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <ProgressPage />
        </MemoryRouter>
      </QueryClientProvider>
    </I18nProvider>,
  )
}

const baseProgress = {
  degreeId: '665f2b0f2a3f7b2a1a9a7d01',
  degreeCode: '006',
  degreeName: 'Industrial Engineering',
  catalogYear: 2025,
  completedCredits: 7.5,
  totalRequiredCredits: 155,
  creditsRemaining: 147.5,
  completionPercentage: 4.84,
  completedElectiveCredits: 3.5,
  remainingElectiveCredits: 2.5,
  statusSummary: 'in_progress',
  requirementProgress: [
    {
      requirementGroupId: '006:elective-ds',
      title: 'Data Science electives',
      isMandatory: false,
      status: 'in_progress',
      minCredits: 6,
      creditsCompleted: 3.5,
      creditsRemaining: 2.5,
      eligibilityEnforcement: 'strict_pool',
      completedCourses: [
        {
          courseId: 'c1',
          courseNumber: '00940345',
          courseTitle: 'Sample course',
          creditsEarned: 3.5,
        },
      ],
    },
  ],
  missingRequirements: [
    {
      requirementGroupId: '006:elective-ds',
      title: 'Data Science electives',
      status: 'in_progress',
      creditsCompleted: 3.5,
      creditsRequired: 6,
      creditsRemaining: 2.5,
      isMandatory: false,
    },
  ],
  assumptions: ['Passing grades above 55 count.'],
}

describe('ProgressPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows setup prompt when degree is not selected', async () => {
    vi.mocked(endpoints.progressApi.get).mockRejectedValue(
      new ApiError('Degree required', 400),
    )
    renderProgress()
    expect(
      await screen.findByText(/select a degree program|בחר תוכנית לימודים/i),
    ).toBeInTheDocument()
  })

  it('renders bucket progress using creditsCompleted and minCredits', async () => {
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: baseProgress,
    })
    vi.mocked(endpoints.progressApi.curriculumGraph).mockResolvedValue({
      curriculumGraph: {
        trackSlug: 'track-industrial-engineering-management',
        programCode: '006',
        catalogYear: 2025,
        catalogVersion: '2025-2026',
        viewDefault: 'semester_swimlanes',
        semesterLanes: [],
        nodes: [],
        edges: [],
        bottlenecks: [],
        electiveBuckets: [],
      },
    })
    renderProgress()
    expect(
      await screen.findByRole('heading', { name: /graduation progress|התקדמות לתואר/i }),
    ).toBeInTheDocument()
    expect(screen.getAllByText('Data science electives').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/3\.5\s*\/\s*6/).length).toBeGreaterThan(0)
    expect(screen.getByText('00940345')).toBeInTheDocument()
    expect(screen.getByText(/still needed|עדיין חסר/i)).toBeInTheDocument()
  })

  it('expands elective pool inline from bucket row', async () => {
    const user = userEvent.setup()
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: baseProgress,
    })
    vi.mocked(endpoints.progressApi.curriculumGraph).mockResolvedValue({
      curriculumGraph: {
        trackSlug: 'track-data-information-engineering',
        programCode: '006',
        catalogYear: 2025,
        catalogVersion: '2025-2026',
        viewDefault: 'semester_swimlanes',
        semesterLanes: [],
        nodes: [],
        edges: [],
        bottlenecks: [],
        electiveBuckets: [
          {
            groupId: '006:elective-ds-pool',
            title: 'DS elective pool',
            linkedCreditBucketId: '006:elective-ds',
            rule: { type: 'course_pool', operator: 'choose_credits' },
            courses: [
              { courseNumber: '00940345', title: 'Sample course', credits: 3.5 },
            ],
            courseCount: 1,
            explorerReady: true,
          },
        ],
      },
    })
    renderProgress('he')
    const exploreButton = await screen.findByTestId('explore-pool-006:elective-ds-006:elective-ds-pool')
    await user.click(exploreButton)
    const detail = await screen.findByTestId('elective-pool-detail-006:elective-ds-pool')
    expect(detail).toBeInTheDocument()
    expect(screen.getByText('בריכת בחירה במדעי הנתונים')).toBeInTheDocument()
    expect(detail).toHaveTextContent('00940345')
  })

  it('shows transcript hint when progress has not started', async () => {
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: {
        ...baseProgress,
        statusSummary: 'not_started',
        completedCredits: 0,
        completionPercentage: 0,
        requirementProgress: [],
        missingRequirements: [],
      },
    })
    renderProgress()
    expect(
      await screen.findByText(/add completed courses on your transcript|הוסף קורסים שהושלמו/i),
    ).toBeInTheDocument()
  })
})
