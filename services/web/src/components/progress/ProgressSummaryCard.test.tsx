import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ProgressSummaryCard } from './ProgressSummaryCard'
import type { GraduationProgress } from '../../types/api'

const t = (key: string) => {
  const labels: Record<string, string> = {
    'progress.summarySubtitle': 'Progress toward your degree requirements',
    'progress.creditsTowardDegree': 'Credits toward your degree',
    'progress.creditsRemainingInline': '{count} credits still needed',
    'progress.overallCompletion': 'Overall completion',
    'common.credits': 'credits',
    'progress.creditsRemaining': 'Credits remaining',
    'progress.summaryRemainingHint': 'Until you reach the degree total',
    'progress.electiveProgress': 'Elective credits',
    'progress.summaryElectiveHint': '{remaining} elective credits still open',
    'progress.summaryNoElectiveCredits': 'No elective credits tracked yet',
    'progress.mandatoryRemaining': 'Mandatory courses left',
    'progress.summaryMandatoryHint': 'Required courses not yet satisfied',
    'progress.summaryAttentionLink': 'View {count} items needing attention',
  }
  return labels[key] ?? key
}

const baseProgress: GraduationProgress = {
  degreeId: '1',
  degreeName: 'Industrial Engineering',
  catalogYear: 2025,
  catalogVersion: '2025-2026',
  completedCredits: 7.5,
  totalRequiredCredits: 155,
  creditsRemaining: 147.5,
  completionPercentage: 4.84,
  completedElectiveCredits: 3.5,
  remainingElectiveCredits: 2.5,
  statusSummary: 'in_progress',
}

describe('ProgressSummaryCard', () => {
  it('shows credit-first hero, ring percent, and stat tiles', () => {
    render(
      <ProgressSummaryCard
        progress={baseProgress}
        statusLabel="In progress"
        mandatoryRemainingCount={2}
        t={t}
      />,
    )

    expect(screen.getByTestId('progress-summary-card')).toBeInTheDocument()
    expect(screen.getByTestId('progress-credits-hero')).toHaveTextContent('7.5')
    expect(screen.getByTestId('progress-credits-hero')).toHaveTextContent('155')
    expect(screen.getByText('4.8%')).toBeInTheDocument()
    expect(screen.getByText(/Industrial Engineering · 2025 · v2025-2026/)).toBeInTheDocument()
    expect(screen.getByText('Credits remaining')).toBeInTheDocument()
    expect(screen.getByText('Elective credits')).toBeInTheDocument()
    expect(screen.getByText('Mandatory courses left')).toBeInTheDocument()
    expect(screen.getByText('147.5')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.queryByText('Open buckets')).not.toBeInTheDocument()
    expect(screen.queryByText('Track status')).not.toBeInTheDocument()
  })

  it('shows attention link when attentionCount is positive', () => {
    render(
      <ProgressSummaryCard
        progress={baseProgress}
        statusLabel="In progress"
        attentionCount={3}
        t={t}
      />,
    )

    expect(screen.getByTestId('progress-summary-attention-link')).toHaveTextContent('3')
  })

  it('shows not-started status with zero completion bar', () => {
    render(
      <ProgressSummaryCard
        progress={{
          ...baseProgress,
          statusSummary: 'not_started',
          completedCredits: 0,
          completionPercentage: 0,
          creditsRemaining: 155,
          completedElectiveCredits: 0,
          remainingElectiveCredits: 0,
        }}
        statusLabel="Not started"
        t={t}
      />,
    )

    expect(screen.getByText('0.0%')).toBeInTheDocument()
    expect(screen.getAllByText('155').length).toBeGreaterThan(0)
    expect(screen.getByText('No elective credits tracked yet')).toBeInTheDocument()
  })

  it('caps completion percentage display at 100%', () => {
    render(
      <ProgressSummaryCard
        progress={{
          ...baseProgress,
          completionPercentage: 104.2,
          completedCredits: 160,
          creditsRemaining: 0,
        }}
        statusLabel="Complete"
        t={t}
      />,
    )

    expect(screen.getByText('100.0%')).toBeInTheDocument()
  })

  it('omits catalog subtitle line when degree metadata is sparse', () => {
    render(
      <ProgressSummaryCard
        progress={{
          ...baseProgress,
          degreeName: undefined,
          degreeCode: undefined,
          catalogYear: undefined,
          catalogVersion: undefined,
        }}
        statusLabel="In progress"
        t={t}
      />,
    )

    expect(screen.queryByText(/Industrial Engineering/)).not.toBeInTheDocument()
    expect(screen.getByText('Progress toward your degree requirements')).toBeInTheDocument()
  })
})
