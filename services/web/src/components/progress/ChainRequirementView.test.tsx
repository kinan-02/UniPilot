import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { I18nProvider } from '../../i18n'
import { ChainRequirementView } from './ChainRequirementView'
import { requirementBucket } from '../../testFixtures/progress'
import type { ElectiveBucket } from '../../types/api'

const t = (key: string) => {
  const labels: Record<string, string> = {
    'progress.electiveExplorer.chainStepHeading': 'Part',
    'progress.electiveExplorer.chainStepStatus.done': 'Done',
    'progress.electiveExplorer.chainStepStatus.pending': 'Pending',
    'progress.electiveExplorer.chainStepEmpty': 'No courses listed',
    'progress.electiveExplorer.counted': 'Counted',
    'progress.electiveExplorer.requiredCourse': 'Required',
    'progress.electiveExplorer.openCatalog': 'Open catalog',
    'progress.electiveExplorer.chainStepNotes.ie-focus-chain-game-theory-part-1':
      'Choose one from Part 1 list',
  }
  return labels[key] ?? key
}

const gameTheoryPool: ElectiveBucket = {
  groupId: 'track-industrial-engineering:ie-focus-chain-game-theory',
  title: 'IE game theory focus chain',
  linkedCreditBucketId: '009216-1-000:elective-faculty',
  rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3, chain: 'game_theory' },
  courses: [
    { courseNumber: '0960226', title: 'Game theory 1', credits: 3 },
    { courseNumber: '0960570', title: 'Game theory 2', credits: 3 },
    { courseNumber: '0960606', title: 'Behavioral econ', credits: 3 },
    { courseNumber: '0960617', title: 'Industrial org', credits: 3 },
    { courseNumber: '0960211', title: 'Commerce', credits: 3 },
  ],
  courseCount: 5,
  explorerReady: true,
}

function renderChainView(countedNumbers = new Set<string>()) {
  return render(
    <I18nProvider>
      <MemoryRouter>
        <ChainRequirementView
          pool={gameTheoryPool}
          bucket={requirementBucket({
            requirementGroupId: '009216-1-000:elective-faculty',
            isMandatory: false,
          })}
          transcriptNumbers={countedNumbers}
          requiredCurriculumNumbers={new Set()}
          t={t}
        />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('ChainRequirementView', () => {
  it('renders structured chain steps for a focus chain pool', () => {
    renderChainView()

    expect(
      screen.getByTestId(`chain-requirement-view-${gameTheoryPool.groupId}`),
    ).toBeInTheDocument()
    expect(screen.getAllByTestId(/^chain-step-/).length).toBe(3)
    expect(screen.getByTestId('chain-step-p1')).toHaveTextContent('0960226')
    expect(screen.getByRole('link', { name: /open catalog/i })).toBeInTheDocument()
  })

  it('shows pending badges when no chain courses are counted', () => {
    renderChainView()

    expect(screen.getAllByText('Pending').length).toBeGreaterThan(0)
  })

  it('marks completed chain steps when transcript includes counted courses', () => {
    renderChainView(new Set(['0960226']))

    const doneBadges = screen.getAllByText('Done')
    expect(doneBadges.length).toBeGreaterThan(0)
  })
})
