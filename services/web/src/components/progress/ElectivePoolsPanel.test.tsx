import { describe, expect, it, vi, type ComponentProps } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { I18nProvider } from '../../i18n'
import { ElectivePoolsPanel } from './ElectivePoolsPanel'
import {
  baseGraduationProgress,
  electivePool,
  generalTechnionPools,
  progressT,
  requirementBucket,
} from '../../testFixtures/progress'

function renderPanel(overrides: Partial<ComponentProps<typeof ElectivePoolsPanel>> = {}) {
  const buckets = baseGraduationProgress().requirementProgress ?? []
  const pools = [electivePool(), ...generalTechnionPools()]
  const props: ComponentProps<typeof ElectivePoolsPanel> = {
    pools,
    requirementBuckets: buckets,
    requiredCurriculumNumbers: new Set(['00940345']),
    transcriptNumbers: new Set(['00940411']),
    expandedPoolId: null,
    t: progressT,
    onExpandedPoolChange: vi.fn(),
    ...overrides,
  }
  return render(
    <I18nProvider>
      <MemoryRouter>
        <ElectivePoolsPanel {...props} />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('ElectivePoolsPanel', () => {
  it('renders program pools above the General Technion section', () => {
    renderPanel()

    expect(screen.getByTestId('elective-pools-panel')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /elective pools & chains/i })).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { name: /general technion requirements/i }),
    ).toBeInTheDocument()

    const panel = screen.getByTestId('elective-pools-panel')
    const programCard = screen.getByTestId(`elective-pool-card-${electivePool().groupId}`)
    const generalHeading = screen.getByRole('heading', {
      name: /general technion requirements/i,
    })
    expect(panel.compareDocumentPosition(programCard) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(
      generalHeading.compareDocumentPosition(programCard) & Node.DOCUMENT_POSITION_PRECEDING,
    ).toBeTruthy()
  })

  it('filters pools by search query and shows empty state when nothing matches', async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.type(screen.getByPlaceholderText(/search pools/i), 'physical education')
    expect(screen.queryByTestId(`elective-pool-card-${electivePool().groupId}`)).not.toBeInTheDocument()
    expect(screen.getByTestId(`elective-pool-card-${generalTechnionPools()[2]!.groupId}`)).toBeInTheDocument()

    await user.clear(screen.getByPlaceholderText(/search pools/i))
    await user.type(screen.getByPlaceholderText(/search pools/i), 'zzzz-no-match')
    expect(screen.getByText(/no pools match "zzzz-no-match"/i)).toBeInTheDocument()
  })

  it('calls onExpandedPoolChange when a pool is toggled', async () => {
    const user = userEvent.setup()
    const onExpandedPoolChange = vi.fn()
    const buckets = baseGraduationProgress().requirementProgress ?? []
    renderPanel({ onExpandedPoolChange })

    const poolCard = screen.getByTestId(`elective-pool-card-${electivePool().groupId}`)
    await user.click(poolCard.querySelector('button[aria-expanded="false"]')!)

    expect(onExpandedPoolChange).toHaveBeenCalledTimes(1)
    expect(onExpandedPoolChange.mock.calls[0]?.[1]?.groupId).toBe(electivePool().groupId)
    expect(onExpandedPoolChange.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({ requirementGroupId: `${requirementBucket().requirementGroupId.split(':')[0]}:elective-ds` }),
    )
  })

  it('expands pool inline and lists eligible courses', async () => {
    const user = userEvent.setup()
    renderPanel({
      expandedPoolId: `${electivePool().groupId}`,
    })

    const detail = screen.getByTestId(`elective-pool-detail-${electivePool().groupId}`)
    expect(detail).toBeInTheDocument()
    expect(detail).toHaveTextContent('00940345')
  })

  it('returns null when no explorer-ready pools exist', () => {
    const { container } = renderPanel({ pools: [] })
    expect(container).toBeEmptyDOMElement()
  })

  it('hides unselected focus chains when transcript progress indicates a chosen track', () => {
    const focusPools = [
      {
        groupId: '009118-1-000:is-focus-chain-performance',
        title: 'Performance chain',
        rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
        courses: [{ courseNumber: '00960327', title: 'Part 1', credits: 3.5 }],
        courseCount: 1,
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        explorerReady: true,
      },
      {
        groupId: '009118-1-000:is-focus-chain-ml',
        title: 'ML chain',
        rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
        courses: [{ courseNumber: '0970209', title: 'ML core', credits: 3.5 }],
        courseCount: 1,
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        explorerReady: true,
      },
    ] as const

    renderPanel({
      pools: [...focusPools],
      requirementBuckets: [
        requirementBucket({
          requirementGroupId: '009118-1-000:elective-faculty',
          isMandatory: false,
          eligibilityEnforcement: 'strict_pool',
          minCredits: 24.5,
          creditsCompleted: 3.5,
          creditsRemaining: 21,
          completedCourses: [{ courseId: 'ml-1', courseNumber: '0970209', creditsEarned: 3.5 }],
        }),
      ],
      transcriptNumbers: new Set(),
      t: (key, params) => {
        if (key === 'progress.electiveExplorer.hiddenChainOptions') {
          return `${params?.count ?? 0} other focus chain options are hidden`
        }
        return progressT(key)
      },
    })

    expect(
      screen.getByTestId('elective-pool-card-009118-1-000:is-focus-chain-ml'),
    ).toBeInTheDocument()
    expect(
      screen.queryByTestId('elective-pool-card-009118-1-000:is-focus-chain-performance'),
    ).not.toBeInTheDocument()
    expect(screen.getByText(/other focus chain options are hidden/i)).toBeInTheDocument()
  })
})
