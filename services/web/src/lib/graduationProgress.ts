import type { GraduationProgress, IneligibleCreditEntry, RequirementProgressEntry } from '../types/api'

export const GENERAL_TECHNION_BUCKET_SUFFIXES = new Set([
  'enrichment',
  'free-elective',
  'physical-education',
])

export const ELECTIVE_CREDIT_BUCKET_SUFFIXES = new Set([
  'elective-ds',
  'elective-faculty',
  'faculty-electives',
  'elective-general',
])

export function requirementGroupSuffix(
  requirementGroupId: string,
): string {
  const separator = requirementGroupId.indexOf(':')
  return separator >= 0 ? requirementGroupId.slice(separator + 1) : requirementGroupId
}

export function isGeneralTechnionBucket(
  bucket: Pick<RequirementProgressEntry, 'requirementGroupId'>,
): boolean {
  return GENERAL_TECHNION_BUCKET_SUFFIXES.has(requirementGroupSuffix(bucket.requirementGroupId))
}

export function isElectiveCreditBucket(
  bucket: Pick<RequirementProgressEntry, 'requirementGroupId'>,
): boolean {
  return ELECTIVE_CREDIT_BUCKET_SUFFIXES.has(requirementGroupSuffix(bucket.requirementGroupId))
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
  const elective = remaining.filter(isElectiveCreditBucket)
  const mandatory = remaining.filter((entry) => !isElectiveCreditBucket(entry))
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

/** Remaining mandatory courses as computed by the API — do not re-filter client-side. */
export function apiRemainingMandatoryCourses(
  progress: GraduationProgress,
): NonNullable<GraduationProgress['remainingMandatoryCourses']> {
  return progress.remainingMandatoryCourses ?? []
}

export function actionableIneligibleCredits(
  progress: GraduationProgress,
): NonNullable<GraduationProgress['ineligibleCredits']> {
  return (progress.ineligibleCredits ?? []).filter(
    (entry) => entry.reason !== 'overlap_no_additional_credit',
  )
}

export function overlapIneligibleCredits(
  progress: GraduationProgress,
): NonNullable<GraduationProgress['ineligibleCredits']> {
  return (progress.ineligibleCredits ?? []).filter(
    (entry) => entry.reason === 'overlap_no_additional_credit',
  )
}

export function hasActionableGaps(progress: GraduationProgress): boolean {
  return Boolean(
    apiRemainingMandatoryCourses(progress).length > 0 ||
      (progress.missingRequirements?.length ?? 0) > 0 ||
      actionableIneligibleCredits(progress).length > 0,
  )
}

export function countAttentionItems(progress: GraduationProgress): number {
  return (
    apiRemainingMandatoryCourses(progress).length +
    (progress.missingRequirements?.length ?? 0) +
    actionableIneligibleCredits(progress).length +
    overlapIneligibleCredits(progress).length
  )
}

export function hasDegreeCreditBucketGap(progress: GraduationProgress): boolean {
  const remainingMandatory = apiRemainingMandatoryCourses(progress)
  const highCompletion =
    progress.completionPercentage >= 99.9 || progress.creditsRemaining <= 0.01
  const openBuckets = (progress.missingRequirements?.length ?? 0) > 0
  const bucketAppliedGap =
    progress.degreeAppliedCredits != null &&
    progress.completedCredits - progress.degreeAppliedCredits > 0.01
  const hasIneligible = actionableIneligibleCredits(progress).length > 0

  if (remainingMandatory.length > 0 && highCompletion) {
    return true
  }

  if (!openBuckets) return false
  return highCompletion || bucketAppliedGap || hasIneligible
}

export function ineligibleCreditReasonLabel(
  reason: string | undefined,
  t: (key: string) => string,
): string {
  if (!reason) {
    return t('progress.ineligibleReasons.unknown')
  }
  const key = `progress.ineligibleReasons.${reason}`
  const translated = t(key)
  return translated !== key ? translated : reason.replace(/_/g, ' ')
}

export function ineligibleCoursePrimaryLabel(
  entry: Pick<IneligibleCreditEntry, 'courseNumber' | 'courseTitle' | 'courseId'>,
): string {
  if (entry.courseNumber) return entry.courseNumber
  if (entry.courseTitle) return entry.courseTitle
  return ''
}

export function ineligibleCourseSecondaryLabel(
  entry: Pick<IneligibleCreditEntry, 'courseNumber' | 'courseTitle'>,
): string | null {
  if (entry.courseNumber && entry.courseTitle) return entry.courseTitle
  return null
}
