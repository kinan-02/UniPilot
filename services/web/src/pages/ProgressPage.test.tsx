import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ProgressPage } from './ProgressPage'
import * as endpoints from '../api/endpoints'
import {
  baseGraduationProgress,
  emptyCurriculumGraph,
  electivePool,
  generalTechnionPools,
} from '../testFixtures/progress'
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
      requirementGroupId: '006:core-math',
      title: 'Core mathematics',
      isMandatory: true,
      status: 'in_progress',
      minCredits: 12,
      creditsCompleted: 7.5,
      creditsRemaining: 4.5,
      eligibilityEnforcement: 'credit_bucket_only',
      completedCourses: [
        {
          courseId: 'c1',
          courseNumber: '00940345',
          courseTitle: 'Sample course',
          creditsEarned: 7.5,
        },
      ],
    },
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
          courseId: 'c2',
          courseNumber: '00940411',
          courseTitle: 'Elective sample',
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

  it('renders mandatory bucket progress and enhanced summary stats', async () => {
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
    expect(screen.getByTestId('progress-summary-card')).toBeInTheDocument()
    expect(screen.getByText('Core mathematics')).toBeInTheDocument()
    expect(screen.getAllByText(/7\.5\s*\/\s*12/).length).toBeGreaterThan(0)
    expect(screen.getByText('00940345')).toBeInTheDocument()
    expect(screen.getByText(/credits remaining|נק״ז שנותרו/i)).toBeInTheDocument()
    expect(screen.queryByText(/still needed|עדיין חסר/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /elective buckets/i })).not.toBeInTheDocument()
  })

  it('expands elective pool inline from the pool explorer', async () => {
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
    const poolCard = await screen.findByTestId('elective-pool-card-006:elective-ds-pool')
    await user.click(poolCard.querySelector('button')!)
    const detail = await screen.findByTestId('elective-pool-detail-006:elective-ds-pool')
    expect(detail).toBeInTheDocument()
    expect(screen.getByText('בריכת בחירה במדעי הנתונים')).toBeInTheDocument()
    expect(detail).toHaveTextContent('00940345')
  })

  it('hides transcript hint once completed credits are recorded', async () => {
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: baseProgress,
    })
    renderProgress()
    await screen.findByTestId('progress-summary-card')
    expect(
      screen.queryByText(/add completed courses on your transcript|הוסף קורסים שהושלמו/i),
    ).not.toBeInTheDocument()
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

  it('shows onboarding link when profile is missing', async () => {
    vi.mocked(endpoints.progressApi.get).mockRejectedValue(
      new ApiError('Student profile not found', 404),
    )
    renderProgress()
    expect(
      await screen.findByText(/add your degree program to unlock|השלם את הפרופיל/i),
    ).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /set up profile|הגדרת פרופיל/i })).toHaveAttribute(
      'href',
      '/onboarding',
    )
  })

  it('shows load failed empty state for unexpected errors', async () => {
    vi.mocked(endpoints.progressApi.get).mockRejectedValue(new ApiError('Server error', 500))
    renderProgress()
    expect(
      await screen.findByText(/unable to load graduation progress|לא ניתן לטעון/i),
    ).toBeInTheDocument()
  })

  it('shows curriculum graph error card when explorer data fails', async () => {
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: baseProgress,
    })
    vi.mocked(endpoints.progressApi.curriculumGraph).mockRejectedValue(
      new ApiError('Graph unavailable', 404),
    )
    renderProgress()
    expect(await screen.findByTestId('progress-summary-card')).toBeInTheDocument()
    expect(
      await screen.findByText(/unable to load elective pools|לא ניתן לטעון/i),
    ).toBeInTheDocument()
  })

  it('renders General Technion pools section below faculty pools', async () => {
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: baseProgress,
    })
    vi.mocked(endpoints.progressApi.curriculumGraph).mockResolvedValue({
      curriculumGraph: emptyCurriculumGraph({
        electiveBuckets: [electivePool(), ...generalTechnionPools()],
      }),
    })
    renderProgress('en')
    expect(await screen.findByTestId('elective-pools-panel')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /general technion requirements/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/university enrichment \(che\)/i)).toBeInTheDocument()
  })

  it('does not render removed elective or general Technion bucket cards', async () => {
    vi.mocked(endpoints.progressApi.get).mockResolvedValue({
      graduationProgress: {
        ...baseProgress,
        requirementProgress: [
          ...baseProgress.requirementProgress,
          {
            requirementGroupId: '006:enrichment',
            title: 'University enrichment',
            isMandatory: false,
            status: 'not_started',
            minCredits: 6,
            creditsCompleted: 0,
            creditsRemaining: 6,
            eligibilityEnforcement: 'strict_pool',
            completedCourses: [],
          },
        ],
      },
    })
    vi.mocked(endpoints.progressApi.curriculumGraph).mockResolvedValue({
      curriculumGraph: emptyCurriculumGraph({
        electiveBuckets: [electivePool(), ...generalTechnionPools()],
      }),
    })
    renderProgress()
    await screen.findByTestId('elective-pools-panel')
    expect(screen.queryByRole('heading', { name: /elective buckets/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /general technion buckets/i })).not.toBeInTheDocument()
  })
})
