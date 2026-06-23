import type { GraduationProgress, RequirementProgressEntry } from '../types/api'

export const GENERAL_TECHNION_BUCKET_SUFFIXES = new Set([
  'enrichment',
  'free-elective',
  'physical-education',
])

export function isGeneralTechnionBucket(
  bucket: Pick<RequirementProgressEntry, 'requirementGroupId'>,
): boolean {
  const separator = bucket.requirementGroupId.indexOf(':')
  const suffix =
    separator >= 0 ? bucket.requirementGroupId.slice(separator + 1) : bucket.requirementGroupId
  return GENERAL_TECHNION_BUCKET_SUFFIXES.has(suffix)
}

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
  const generalTechnion = requirementProgress
    .filter(isGeneralTechnionBucket)
    .sort((left, right) => {
      const order = ['enrichment', 'free-elective', 'physical-education']
      const leftSuffix = left.requirementGroupId.slice(left.requirementGroupId.indexOf(':') + 1)
      const rightSuffix = right.requirementGroupId.slice(right.requirementGroupId.indexOf(':') + 1)
      return order.indexOf(leftSuffix) - order.indexOf(rightSuffix)
    })
  const remaining = requirementProgress.filter((entry) => !isGeneralTechnionBucket(entry))
  const mandatory = remaining.filter((entry) => entry.isMandatory !== false)
  const elective = remaining.filter((entry) => entry.isMandatory === false)
  return { mandatory, elective, generalTechnion }
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
