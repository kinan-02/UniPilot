import { describe, expect, it } from 'vitest'
import { buildWatchdogLink } from './watchdogLinks'
import type { AiRecommendation } from '../types/api'

function recommendation(overrides: Partial<AiRecommendation> = {}): AiRecommendation {
  return {
    id: 'rec1',
    type: 'watchdog_nudge',
    title: 'Alert',
    body: 'Details',
    ...overrides,
  }
}

describe('buildWatchdogLink', () => {
  it('routes pace nudges to progress attention anchor', () => {
    const link = buildWatchdogLink(recommendation({ nudgeType: 'pace' }))
    expect(link.to).toBe('/progress#progress-attention')
    expect(link.labelKey).toBe('watchdog.actionReviewProgress')
  })

  it('routes prereq nudges to the linked plan when available', () => {
    const link = buildWatchdogLink(
      recommendation({ nudgeType: 'prereq', planId: 'plan-123' }),
    )
    expect(link.to).toBe('/plans/plan-123')
    expect(link.labelKey).toBe('watchdog.actionOpenPlan')
  })

  it('routes risk nudges to risks page', () => {
    const link = buildWatchdogLink(recommendation({ nudgeType: 'risk' }))
    expect(link.to).toBe('/risks')
    expect(link.labelKey).toBe('watchdog.actionViewRisks')
  })
})
