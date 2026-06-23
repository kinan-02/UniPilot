import { describe, expect, it, vi, type ComponentProps } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { I18nProvider } from '../../i18n'
import { ElectivePoolRow } from './ElectivePoolRow'
import {
  baseGraduationProgress,
  electivePool,
  progressT,
  requirementBucket,
} from '../../testFixtures/progress'

function renderRow(overrides: Partial<ComponentProps<typeof ElectivePoolRow>> = {}) {
  const pool = electivePool()
  const buckets = baseGraduationProgress().requirementProgress ?? []
  const props: ComponentProps<typeof ElectivePoolRow> = {
    pool,
    allPools: [pool],
    requirementBuckets: buckets,
    requiredCurriculumNumbers: new Set(['00940345']),
    transcriptNumbers: new Set(['00940411']),
    expanded: false,
    t: progressT,
    onToggle: vi.fn(),
    ...overrides,
  }
  return render(
    <I18nProvider>
      <MemoryRouter>
        <ElectivePoolRow {...props} />
      </MemoryRouter>
    </I18nProvider>,
  )
}

describe('ElectivePoolRow', () => {
  it('renders collapsed pool card with localized title and toggle', () => {
    renderRow()

    const card = screen.getByTestId(`elective-pool-card-${electivePool().groupId}`)
    expect(card).toBeInTheDocument()
    expect(screen.getByText(/data science elective pool/i)).toBeInTheDocument()
    expect(card.querySelector('button[aria-expanded="false"]')).toBeTruthy()
    expect(screen.queryByTestId(`elective-pool-detail-${electivePool().groupId}`)).not.toBeInTheDocument()
  })

  it('calls onToggle with linked bucket and pool', async () => {
    const user = userEvent.setup()
    const onToggle = vi.fn()
    renderRow({ onToggle })

    await user.click(
      screen.getByTestId(`elective-pool-card-${electivePool().groupId}`).querySelector('button')!,
    )

    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(onToggle.mock.calls[0]?.[1]?.groupId).toBe(electivePool().groupId)
    expect(onToggle.mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        requirementGroupId: `${requirementBucket().requirementGroupId.split(':')[0]}:elective-ds`,
      }),
    )
  })

  it('shows inline course list when expanded', () => {
    renderRow({ expanded: true })

    const detail = screen.getByTestId(`elective-pool-detail-${electivePool().groupId}`)
    expect(detail).toBeInTheDocument()
    expect(detail).toHaveTextContent('00940345')
  })
})
