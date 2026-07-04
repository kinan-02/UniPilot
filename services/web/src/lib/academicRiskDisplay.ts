import type { AcademicRiskSummary } from '../types/api'

type TranslateFn = (key: string, params?: Record<string, string | number>) => string

function isAcademicRiskSummary(value: unknown): value is AcademicRiskSummary {
  return Boolean(value && typeof value === 'object' && 'totalRisks' in value)
}

export function formatAcademicRiskSummary(
  summary: unknown,
  t: TranslateFn,
  fallback: string,
): string {
  if (typeof summary === 'string' && summary.trim()) {
    return summary
  }

  if (!isAcademicRiskSummary(summary)) {
    return fallback
  }

  const total = summary.totalRisks ?? 0
  if (total === 0) {
    return t('risks.summaryNone')
  }

  const counts = summary.counts ?? {}
  return t('risks.summaryWithCounts', {
    total,
    high: counts.high ?? 0,
    medium: counts.medium ?? 0,
    low: counts.low ?? 0,
    highest: summary.highestSeverity ?? '—',
  })
}
