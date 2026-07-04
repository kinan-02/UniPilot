import { describe, expect, it } from 'vitest'
import { formatAcademicRiskSummary } from './academicRiskDisplay'

const t = (key: string, params?: Record<string, string | number>) => {
  if (key === 'risks.summaryNone') {
    return 'No risks'
  }
  if (key === 'risks.summaryWithCounts' && params) {
    return `${params.total} risks (${params.highest} highest)`
  }
  return key
}

describe('formatAcademicRiskSummary', () => {
  it('returns string summaries unchanged', () => {
    expect(formatAcademicRiskSummary('Custom summary', t, 'fallback')).toBe('Custom summary')
  })

  it('formats structured API summary objects', () => {
    expect(
      formatAcademicRiskSummary(
        {
          totalRisks: 2,
          highestSeverity: 'high',
          counts: { low: 0, medium: 1, high: 1 },
        },
        t,
        'fallback',
      ),
    ).toBe('2 risks (high highest)')
  })

  it('handles zero-risk summary objects', () => {
    expect(
      formatAcademicRiskSummary(
        {
          totalRisks: 0,
          highestSeverity: null,
          counts: { low: 0, medium: 0, high: 0 },
        },
        t,
        'fallback',
      ),
    ).toBe('No risks')
  })
})
