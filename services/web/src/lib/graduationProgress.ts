import type { CurriculumGraph, GraduationProgress, RequirementProgressEntry } from '../types/api'
import { buildMandatoryEquivalenceGroups } from './courseEquivalence'
import { courseNumberKeys } from './courseNumbers'

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

export function hasActionableGaps(
  progress: GraduationProgress,
  curriculumGraph?: CurriculumGraph | null,
): boolean {
  const remainingMandatory = filterRemainingMandatoryCourses(
    progress.remainingMandatoryCourses,
    progress.completedMandatoryCourses,
    curriculumGraph,
  )
  return Boolean(
    remainingMandatory.length > 0 ||
      (progress.missingRequirements?.length ?? 0) > 0 ||
      (progress.ineligibleCredits?.length ?? 0) > 0,
  )
}

export function countAttentionItems(
  progress: GraduationProgress,
  curriculumGraph?: CurriculumGraph | null,
): number {
  const remainingMandatory = filterRemainingMandatoryCourses(
    progress.remainingMandatoryCourses,
    progress.completedMandatoryCourses,
    curriculumGraph,
  )
  return (
    remainingMandatory.length +
    (progress.missingRequirements?.length ?? 0) +
    (progress.ineligibleCredits?.length ?? 0)
  )
}

function mandatoryGroupForCourse(
  courseNumber: string | undefined,
  groups: Array<Set<string>>,
): Set<string> | null {
  if (!courseNumber) return null
  const keys = new Set(courseNumberKeys(courseNumber))
  return groups.find((group) => [...keys].some((key) => group.has(key))) ?? null
}

export function filterRemainingMandatoryCourses(
  remaining: GraduationProgress['remainingMandatoryCourses'],
  completed: GraduationProgress['completedMandatoryCourses'],
  curriculumGraph?: CurriculumGraph | null,
): NonNullable<GraduationProgress['remainingMandatoryCourses']> {
  const completedKeys = new Set<string>()
  for (const course of completed ?? []) {
    for (const key of courseNumberKeys(course.courseNumber ?? '')) {
      completedKeys.add(key)
    }
  }

  const mandatoryGroups = buildMandatoryEquivalenceGroups({
    curriculumGraph,
    remainingMandatory: remaining,
    completedMandatory: completed,
  })
  const satisfiedGroups = new Set<Set<string>>()
  for (const group of mandatoryGroups) {
    if ([...group].some((key) => completedKeys.has(key))) {
      satisfiedGroups.add(group)
    }
  }

  const seenGroups = new Set<Set<string>>()
  const filtered: NonNullable<GraduationProgress['remainingMandatoryCourses']> = []

  for (const course of remaining ?? []) {
    const group = mandatoryGroupForCourse(course.courseNumber, mandatoryGroups)
    if (group) {
      if ([...satisfiedGroups].some((satisfied) => satisfied === group)) continue
      if (seenGroups.has(group)) continue
      if (
        course.courseNumber &&
        courseNumberKeys(course.courseNumber).some((key) => completedKeys.has(key))
      ) {
        continue
      }
      seenGroups.add(group)
      filtered.push(course)
      continue
    }

    if (!course.courseNumber) {
      filtered.push(course)
      continue
    }
    if (!courseNumberKeys(course.courseNumber).some((key) => completedKeys.has(key))) {
      filtered.push(course)
    }
  }

  return filtered
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
