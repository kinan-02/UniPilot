import type { AiRecommendation } from '../types/api'

export type WatchdogLink = {
  to: string
  labelKey: 'watchdog.actionReviewProgress' | 'watchdog.actionOpenPlan' | 'watchdog.actionViewRisks'
}

export function buildWatchdogLink(recommendation: AiRecommendation): WatchdogLink {
  const nudgeType = recommendation.nudgeType ?? recommendation.type

  if (nudgeType === 'prereq') {
    const planId = recommendation.planId
    return {
      to: planId ? `/plans/${planId}` : '/plans',
      labelKey: 'watchdog.actionOpenPlan',
    }
  }

  if (nudgeType === 'risk') {
    return {
      to: '/risks',
      labelKey: 'watchdog.actionViewRisks',
    }
  }

  return {
    to: '/progress#progress-attention',
    labelKey: 'watchdog.actionReviewProgress',
  }
}
