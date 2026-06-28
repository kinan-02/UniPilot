import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CurriculumGraphSection } from './CurriculumGraphSection'
import { emptyCurriculumGraph } from '../../testFixtures/progress'

const t = (key: string) => {
  const labels: Record<string, string> = {
    'progress.curriculum.title': 'Required curriculum',
    'progress.curriculum.subtitle': 'Recommended semester layout from the catalog vault.',
    'progress.curriculum.expandMindMap': 'Mind map view',
    'progress.curriculum.collapseView': 'Collapse view',
    'progress.curriculum.credits': 'Credits',
    'progress.curriculum.verifyCredits': 'verify with registrar',
    'progress.curriculum.status.available': 'Available',
    'progress.curriculum.status.completed': 'Completed',
  }
  return labels[key] ?? key
}

describe('CurriculumGraphSection', () => {
  it('renders section header, preview stats, and collapsed state by default', () => {
    render(<CurriculumGraphSection graph={emptyCurriculumGraph()} t={t} />)

    expect(screen.getByTestId('curriculum-graph-section')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /required curriculum/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /mind map view/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    )
    expect(screen.queryByTestId('curriculum-mindmap')).not.toBeInTheDocument()
    expect(screen.getByTestId('curriculum-graph-preview')).toBeInTheDocument()
  })

  it('expands mind map and renders curriculum nodes', async () => {
    const user = userEvent.setup()
    render(<CurriculumGraphSection graph={emptyCurriculumGraph()} t={t} />)

    await user.click(screen.getByRole('button', { name: /mind map view/i }))

    expect(screen.getByRole('button', { name: /collapse view/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
    expect(screen.getByTestId('curriculum-mindmap')).toBeInTheDocument()
    expect(screen.getByTestId('curriculum-node-00940345')).toBeInTheDocument()
    expect(screen.getByTestId('curriculum-node-01040031')).toBeInTheDocument()
  })

  it('collapses mind map when toggle is clicked again', async () => {
    const user = userEvent.setup()
    render(<CurriculumGraphSection graph={emptyCurriculumGraph()} t={t} />)

    await user.click(screen.getByRole('button', { name: /mind map view/i }))
    await user.click(screen.getByRole('button', { name: /collapse view/i }))

    expect(screen.queryByTestId('curriculum-mindmap')).not.toBeInTheDocument()
  })

  it('shows completed-via-alternative note on curriculum nodes', async () => {
    const user = userEvent.setup()
    render(
      <CurriculumGraphSection
        graph={emptyCurriculumGraph({
          nodes: [
            {
              nodeId: 'node-algebra',
              courseNumber: '1040065',
              title: 'Algebra',
              semester: 1,
              status: 'completed',
              credits: { display: '5', value: 5, uncertain: false },
              alternatives: ['1040016'],
              satisfiedViaAlternative: '01040016',
              dataQuality: {
                manualReviewRequired: false,
                confidence: 'high',
                hasAlternatives: true,
                creditsUncertain: false,
                verifyWithRegistrar: true,
              },
              prerequisiteNumbers: [],
              missingPrerequisites: [],
              isBottleneck: false,
            },
          ],
          semesterLanes: [
            {
              semester: 1,
              title: 'Year 1 — Semester 1',
              nodeIds: ['node-algebra'],
              collapsedByDefault: false,
            },
          ],
        })}
        t={(key, params) => {
          if (key === 'progress.curriculum.satisfiedViaAlternative') {
            return `Completed via parallel course ${params?.courseNumber ?? ''}`
          }
          return t(key)
        }}
      />,
    )

    await user.click(screen.getByRole('button', { name: /mind map view/i }))
    expect(screen.getByText(/completed via parallel course 01040016/i)).toBeInTheDocument()
  })
})
