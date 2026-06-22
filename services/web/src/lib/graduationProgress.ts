import type { GraduationProgress, RequirementProgressEntry } from '../types/api'

export function bucketCompletionPercent(
  creditsCompleted: number,
  minCredits: number,
): number {
  if (minCredits <= 0) return creditsCompleted > 0 ? 100 : 0
  return Math.min(100, (creditsCompleted / minCredits) * 100)
}

export function statusBadgeTone(
  status: string,
): 'success' | 'warning' | 'primary' | 'neutral' | 'danger' {
  switch (status) {
    case 'complete':
    case 'satisfied':
    case 'mandatory_requirements_met':
      return 'success'
    case 'in_progress':
      return 'primary'
    case 'not_started':
      return 'neutral'
    default:
      return 'warning'
  }
}

export function partitionRequirementBuckets(requirementProgress: RequirementProgressEntry[] = []) {
  const mandatory = requirementProgress.filter((entry) => entry.isMandatory !== false)
  const elective = requirementProgress.filter((entry) => entry.isMandatory === false)
  return { mandatory, elective }
}

export function progressCatalogSubtitle(progress: GraduationProgress): string {
  const parts: string[] = []
  if (progress.degreeName) parts.push(progress.degreeName)
  else if (progress.degreeCode) parts.push(progress.degreeCode)
  if (progress.catalogYear) {
    parts.push(
      progress.catalogVersion
        ? `${progress.catalogYear} · v${progress.catalogVersion}`
        : String(progress.catalogYear),
    )
  }
  return parts.join(' · ') || ''
}

export function hasActionableGaps(progress: GraduationProgress): boolean {
  return Boolean(
    (progress.remainingMandatoryCourses?.length ?? 0) > 0 ||
      (progress.missingRequirements?.length ?? 0) > 0 ||
      (progress.ineligibleCredits?.length ?? 0) > 0,
  )
}
