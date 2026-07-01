import { buildChainRequirementView } from './chainRequirementSteps'
import { courseNumberKeys } from './courseNumbers'
import {
  groupSuffix,
  isChainPool,
  poolCountedCourseNumbers,
  progressBucketForPool,
} from './electivePools'
import type {
  CurriculumGraph,
  ElectiveBucket,
  GraduationProgress,
  RequirementProgressEntry,
} from '../types/api'
import { buildCourseEquivalenceGroups, expandNumbersWithEquivalence } from './courseEquivalence'

export type ChainEngagement = {
  satisfiedSteps: number
  totalSteps: number
  countedCourses: number
  hasProgress: boolean
}

/** Pools that belong to the same pick-one-of-N chain requirement. */
export function exclusiveChainGroupKey(pool: ElectiveBucket): string | null {
  if (pool.rule.operator !== 'choose_chain') return null

  const separator = pool.groupId.indexOf(':')
  const programCode = separator >= 0 ? pool.groupId.slice(0, separator) : pool.groupId
  const suffix = groupSuffix(pool.groupId)

  if (/^(ie|is)-focus-chain-/.test(suffix)) {
    return `${programCode}:focus-chain`
  }
  if (/^cs-science-chain-/.test(suffix)) {
    return `${programCode}:science-chain`
  }
  if (pool.linkedCreditBucketId) {
    return `${pool.linkedCreditBucketId}:choose_chain`
  }
  return null
}

export function groupExclusiveChainPools(pools: ElectiveBucket[]): Map<string, ElectiveBucket[]> {
  const grouped = new Map<string, ElectiveBucket[]>()
  for (const pool of pools) {
    const key = exclusiveChainGroupKey(pool)
    if (!key) continue
    const list = grouped.get(key) ?? []
    list.push(pool)
    grouped.set(key, list)
  }
  return grouped
}

function fallbackBucket(pool: ElectiveBucket): RequirementProgressEntry {
  return {
    requirementGroupId: pool.linkedCreditBucketId ?? pool.groupId,
    title: pool.title,
    status: 'not_started',
    minCredits: pool.minCredits ?? 0,
    creditsCompleted: 0,
    creditsRemaining: pool.minCredits ?? 0,
  }
}

export function chainEngagement(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  transcriptNumbers: Set<string>,
  t: (key: string) => string,
  allPools: ElectiveBucket[] = [],
  curriculumGraph?: CurriculumGraph | null,
  graduationProgress?: GraduationProgress | null,
): ChainEngagement {
  const bucketCounted = poolCountedCourseNumbers(pool, bucket, allPools)
  const equivalenceGroups = buildCourseEquivalenceGroups({
    curriculumGraph,
    progress: graduationProgress,
    poolCourses: pool.courses,
  })
  const expandedTranscript = expandNumbersWithEquivalence(transcriptNumbers, equivalenceGroups)
  const engagementNumbers = new Set(bucketCounted)
  for (const course of pool.courses) {
    if (courseNumberKeys(course.courseNumber).some((key) => expandedTranscript.has(key))) {
      engagementNumbers.add(course.courseNumber)
    }
  }
  const expandedBucketCounted = expandNumbersWithEquivalence(bucketCounted, equivalenceGroups)
  const view = buildChainRequirementView(pool, t, expandedBucketCounted)

  if (!view) {
    return {
      satisfiedSteps: 0,
      totalSteps: 0,
      countedCourses: bucketCounted.size,
      hasProgress: bucketCounted.size > 0 || engagementNumbers.size > 0,
    }
  }

  if (view.layout === 'steps') {
    const satisfiedSteps = view.steps.filter((step) => step.satisfied).length
    return {
      satisfiedSteps,
      totalSteps: view.steps.length,
      countedCourses: bucketCounted.size,
      hasProgress: satisfiedSteps > 0 || bucketCounted.size > 0 || engagementNumbers.size > 0,
    }
  }

  const bestChain = [...view.chains].sort(
    (left, right) => right.satisfiedCount - left.satisfiedCount,
  )[0]
  return {
    satisfiedSteps: bestChain?.satisfiedCount ?? 0,
    totalSteps: bestChain?.steps.length ?? 0,
    countedCourses: bucketCounted.size,
    hasProgress:
      (bestChain?.satisfiedCount ?? 0) > 0 ||
      view.chains.some((chain) => chain.satisfiedCount > 0) ||
      bucketCounted.size > 0 ||
      engagementNumbers.size > 0,
  }
}

export function resolveActiveExclusiveChainPool(
  group: ElectiveBucket[],
  requirementBuckets: RequirementProgressEntry[],
  transcriptNumbers: Set<string>,
  t: (key: string) => string,
  allPools: ElectiveBucket[] = [],
  curriculumGraph?: CurriculumGraph | null,
  graduationProgress?: GraduationProgress | null,
): ElectiveBucket | null {
  if (group.length < 2) return null

  const scored = group.map((pool) => {
    const bucket = progressBucketForPool(pool, requirementBuckets) ?? fallbackBucket(pool)
    const engagement = chainEngagement(
      pool,
      bucket,
      transcriptNumbers,
      t,
      allPools,
      curriculumGraph,
      graduationProgress,
    )
    return { pool, engagement }
  })

  const withProgress = scored.filter((entry) => entry.engagement.hasProgress)
  if (!withProgress.length) return null

  withProgress.sort((left, right) => {
    const stepDelta =
      right.engagement.satisfiedSteps - left.engagement.satisfiedSteps
    if (stepDelta !== 0) return stepDelta
    const countedDelta =
      right.engagement.countedCourses - left.engagement.countedCourses
    if (countedDelta !== 0) return countedDelta
    return left.pool.groupId.localeCompare(right.pool.groupId)
  })

  return withProgress[0]?.pool ?? null
}

export function filterPoolsByExclusiveChainSelection(
  pools: ElectiveBucket[],
  requirementBuckets: RequirementProgressEntry[],
  transcriptNumbers: Set<string>,
  t: (key: string) => string,
  options?: {
    showAllChainOptions?: boolean
    curriculumGraph?: CurriculumGraph | null
    graduationProgress?: GraduationProgress | null
  },
): { pools: ElectiveBucket[]; hiddenExclusiveChainCount: number } {
  if (options?.showAllChainOptions) {
    return { pools, hiddenExclusiveChainCount: 0 }
  }

  const groups = groupExclusiveChainPools(pools.filter(isChainPool))
  const hiddenIds = new Set<string>()

  for (const group of groups.values()) {
    if (group.length < 2) continue
    const active = resolveActiveExclusiveChainPool(
      group,
      requirementBuckets,
      transcriptNumbers,
      t,
      pools,
      options?.curriculumGraph,
      options?.graduationProgress,
    )
    if (!active) continue
    for (const pool of group) {
      if (pool.groupId !== active.groupId) {
        hiddenIds.add(pool.groupId)
      }
    }
  }

  return {
    pools: pools.filter((pool) => !hiddenIds.has(pool.groupId)),
    hiddenExclusiveChainCount: hiddenIds.size,
  }
}
