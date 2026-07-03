import type {
  CurriculumGraph,
  ElectiveBucket,
  ElectivePoolCourse,
  GraduationProgress,
  RequirementProgressEntry,
} from '../types/api'
import { courseNumberKeys, canonicalCourseNumber } from './courseNumbers'
import {
  buildCourseEquivalenceGroups,
  dedupeEquivalentPoolCourses,
  expandNumbersWithEquivalence,
  isCountedViaEquivalence,
} from './courseEquivalence'
import { buildChainRequirementView, hasStructuredChainLayout } from './chainRequirementSteps'

export type PoolCategory =
  | 'credit_pool'
  | 'focus_chain'
  | 'choose_n'
  | 'faculty_list'
  | 'general_elective'
  | 'other'

export type PoolProgressDisplay =
  | 'chain_steps'
  | 'dedicated_bucket_credits'
  | 'shared_bucket_credits'
  | 'none'

export type PoolCourseFilter = 'all' | 'counted' | 'remaining'

export type PoolCourseSort = 'catalog' | 'number' | 'title' | 'credits' | 'counted_first'

export type PoolProgressSummary = {
  counted: number
  listed: number
  creditsCompleted: number
  bucketCreditsCompleted: number
  chainStepsCompleted: number
  chainStepsRequired: number | null
}

export function interpolateTemplate(
  template: string,
  vars: Record<string, string | number>,
): string {
  return Object.entries(vars).reduce(
    (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
    template,
  )
}

export function classifyPool(pool: ElectiveBucket): PoolCategory {
  const operator = pool.rule.operator
  const suffix = groupSuffix(pool.groupId)
  if (
    suffix === 'enrichment-pool' ||
    suffix === 'free-elective-pool' ||
    suffix === 'physical-education-pool'
  ) {
    return 'general_elective'
  }
  if (operator === 'choose_chain') return 'focus_chain'
  if (operator === 'choose_n') return 'choose_n'
  if (
    operator === 'choose_credits' ||
    pool.groupId.includes('elective-ds') ||
    pool.groupId.includes('elective-faculty')
  ) {
    return 'credit_pool'
  }
  if (operator === 'min_credits') return 'faculty_list'
  return 'other'
}

export function poolCategoryTranslationKey(category: PoolCategory): string {
  return `progress.electiveExplorer.categories.${category}`
}

const GENERAL_TECHNION_POOL_SUFFIXES = [
  'enrichment-pool',
  'free-elective-pool',
  'physical-education-pool',
] as const

export function isGeneralTechnionPool(
  pool: Pick<ElectiveBucket, 'groupId'>,
): boolean {
  return GENERAL_TECHNION_POOL_SUFFIXES.includes(
    groupSuffix(pool.groupId) as (typeof GENERAL_TECHNION_POOL_SUFFIXES)[number],
  )
}

function generalTechnionPoolSortIndex(groupId: string): number {
  const suffix = groupSuffix(groupId)
  const index = GENERAL_TECHNION_POOL_SUFFIXES.indexOf(
    suffix as (typeof GENERAL_TECHNION_POOL_SUFFIXES)[number],
  )
  return index >= 0 ? index : GENERAL_TECHNION_POOL_SUFFIXES.length
}

export function partitionExplorerPools(pools: ElectiveBucket[]): {
  programPools: ElectiveBucket[]
  generalTechnionPools: ElectiveBucket[]
} {
  const explorerReady = pools.filter((entry) => entry.explorerReady)
  const generalTechnionPools = explorerReady
    .filter(isGeneralTechnionPool)
    .sort(
      (left, right) =>
        generalTechnionPoolSortIndex(left.groupId) -
        generalTechnionPoolSortIndex(right.groupId),
    )
  const generalIds = new Set(generalTechnionPools.map((entry) => entry.groupId))
  const programPools = explorerReady.filter((entry) => !generalIds.has(entry.groupId))
  return { programPools, generalTechnionPools }
}

export function groupPoolsByCategory(
  pools: ElectiveBucket[],
): Array<{ category: PoolCategory; pools: ElectiveBucket[] }> {
  const order: PoolCategory[] = [
    'credit_pool',
    'focus_chain',
    'choose_n',
    'faculty_list',
    'general_elective',
    'other',
  ]
  const grouped = new Map<PoolCategory, ElectiveBucket[]>()

  for (const pool of pools.filter((entry) => entry.explorerReady)) {
    const category = classifyPool(pool)
    const list = grouped.get(category) ?? []
    list.push(pool)
    grouped.set(category, list)
  }

  return order
    .filter((category) => grouped.has(category))
    .map((category) => ({ category, pools: grouped.get(category) ?? [] }))
}

export function findPoolsForBucket(
  bucket: RequirementProgressEntry,
  pools: ElectiveBucket[] | undefined,
): ElectiveBucket[] {
  if (!pools?.length) return []

  const matches: ElectiveBucket[] = []
  const seen = new Set<string>()

  const add = (pool: ElectiveBucket | undefined) => {
    if (!pool?.explorerReady || !pool.groupId || seen.has(pool.groupId)) return
    seen.add(pool.groupId)
    matches.push(pool)
  }

  if (bucket.linkedPoolGroupId) {
    add(pools.find((pool) => pool.groupId === bucket.linkedPoolGroupId))
  }

  for (const pool of pools) {
    if (pool.linkedCreditBucketId === bucket.requirementGroupId) {
      add(pool)
    }
  }

  add(pools.find((pool) => pool.groupId === `${bucket.requirementGroupId}-pool`))

  return matches
}

export function findPoolForBucket(
  bucket: RequirementProgressEntry,
  pools: ElectiveBucket[] | undefined,
): ElectiveBucket | undefined {
  return findPoolsForBucket(bucket, pools)[0]
}

export function progressBucketForPool(
  pool: ElectiveBucket,
  buckets: RequirementProgressEntry[] | undefined,
): RequirementProgressEntry | undefined {
  if (!buckets?.length) return undefined
  if (pool.linkedCreditBucketId) {
    return buckets.find((bucket) => bucket.requirementGroupId === pool.linkedCreditBucketId)
  }
  return undefined
}

export function ruleOperatorTranslationKey(operator: string | null | undefined): string {
  switch (operator) {
    case 'choose_n':
      return 'progress.electiveExplorer.ruleChooseN'
    case 'choose_chain':
      return 'progress.electiveExplorer.ruleChooseChain'
    case 'choose_credits':
      return 'progress.electiveExplorer.ruleChooseCredits'
    case 'min_credits':
      return 'progress.electiveExplorer.ruleMinCredits'
    default:
      return 'progress.electiveExplorer.ruleGeneric'
  }
}

export function ruleBadgeTone(
  operator: string | null | undefined,
): 'primary' | 'success' | 'warning' | 'neutral' {
  switch (operator) {
    case 'choose_chain':
      return 'primary'
    case 'choose_n':
      return 'warning'
    case 'choose_credits':
      return 'success'
    default:
      return 'neutral'
  }
}

export function completedCourseNumberSet(bucket: RequirementProgressEntry): Set<string> {
  const numbers = new Set<string>()
  for (const course of bucket.completedCourses ?? []) {
    if (course.courseNumber) {
      addCourseNumberKeys(numbers, course.courseNumber)
    }
  }
  return numbers
}

export function buildTranscriptCourseNumbers(
  requirementProgress: RequirementProgressEntry[] | undefined,
): Set<string> {
  const numbers = new Set<string>()
  for (const bucket of requirementProgress ?? []) {
    for (const course of bucket.completedCourses ?? []) {
      addCourseNumberKeys(numbers, course.courseNumber)
    }
  }
  return numbers
}

/** All passing transcript course numbers, including ineligible rows not assigned to buckets. */
export function buildFullTranscriptCourseNumbers(
  progress: Pick<
    GraduationProgress,
    'requirementProgress' | 'ineligibleCredits' | 'completedMandatoryCourses'
  >,
): Set<string> {
  const numbers = buildTranscriptCourseNumbers(progress.requirementProgress)
  for (const course of progress.completedMandatoryCourses ?? []) {
    addCourseNumberKeys(numbers, course.courseNumber)
  }
  for (const entry of progress.ineligibleCredits ?? []) {
    addCourseNumberKeys(numbers, entry.courseNumber)
  }
  return numbers
}

/** Course numbers from raw completed-course records (actual transcript). */
export function buildCompletedCourseNumberSet(
  records: Array<{ courseNumber?: string | null }> | undefined,
): Set<string> {
  const numbers = new Set<string>()
  for (const record of records ?? []) {
    addCourseNumberKeys(numbers, record.courseNumber)
  }
  return numbers
}

export function addCourseNumberKeys(numbers: Set<string>, value: string | null | undefined): void {
  if (!value) return
  for (const key of courseNumberKeys(value)) {
    numbers.add(key)
  }
}

export function buildRequiredCurriculumCourseNumbers(
  requirementProgress: RequirementProgressEntry[] | undefined,
  options?: {
    curriculumGraph?: CurriculumGraph | null
    remainingMandatory?: GraduationProgress['remainingMandatoryCourses']
  },
): Set<string> {
  const outstandingKeys = new Set<string>()
  const outstandingNumbers: string[] = []
  const hasApiRemainingList = options?.remainingMandatory !== undefined

  for (const course of options?.remainingMandatory ?? []) {
    if (!course.courseNumber) continue
    outstandingNumbers.push(course.courseNumber)
    addCourseNumberKeys(outstandingKeys, course.courseNumber)
  }

  for (const bucket of requirementProgress ?? []) {
    if (bucket.isMandatory === false) continue
    for (const course of bucket.remainingCourses ?? []) {
      if (!course.courseNumber) continue
      outstandingNumbers.push(course.courseNumber)
      addCourseNumberKeys(outstandingKeys, course.courseNumber)
    }
  }

  const result = new Set<string>()

  if (outstandingNumbers.length > 0) {
    for (const courseNumber of outstandingNumbers) {
      addCourseNumberKeys(result, courseNumber)
    }
    for (const node of options?.curriculumGraph?.nodes ?? []) {
      const members = [node.courseNumber, ...(node.alternatives ?? [])]
      const memberKeys = members.flatMap((member) => [...courseNumberKeys(member)])
      if (!memberKeys.some((key) => outstandingKeys.has(key))) continue
      for (const member of members) {
        addCourseNumberKeys(result, member)
      }
    }
    return result
  }

  if (hasApiRemainingList) {
    return result
  }

  for (const node of options?.curriculumGraph?.nodes ?? []) {
    addCourseNumberKeys(result, node.courseNumber)
    for (const alternative of node.alternatives ?? []) {
      addCourseNumberKeys(result, alternative)
    }
  }

  return result
}

export function isCountedCourse(courseNumber: string, countedNumbers: Set<string>): boolean {
  return courseNumberKeys(courseNumber).some((key) => countedNumbers.has(key))
}

export function isRequiredCurriculumCourse(
  courseNumber: string,
  requiredNumbers: Set<string>,
): boolean {
  return courseNumberKeys(courseNumber).some((key) => requiredNumbers.has(key))
}

export function isFocusChainPool(pool: ElectiveBucket): boolean {
  return pool.rule.operator === 'choose_chain'
}

function explorerPoolsForBucket(
  pool: ElectiveBucket,
  allPools: ElectiveBucket[],
): ElectiveBucket[] {
  if (!pool.linkedCreditBucketId) return [pool]
  return allPools.filter(
    (entry) => entry.explorerReady && entry.linkedCreditBucketId === pool.linkedCreditBucketId,
  )
}

function computePoolProgressDisplay(
  pool: ElectiveBucket,
  allPools: ElectiveBucket[] = [],
): PoolProgressDisplay {
  if (isFocusChainPool(pool)) return 'chain_steps'
  if (pool.rule.operator === 'choose_n') return 'chain_steps'
  const suffix = groupSuffix(pool.groupId)
  const bucketSharers = explorerPoolsForBucket(pool, allPools)
  const soleBucketPool = bucketSharers.length <= 1

  if (
    soleBucketPool &&
    (suffix === 'elective-ds-pool' ||
      suffix === 'elective-faculty-pool' ||
      suffix === 'enrichment-pool' ||
      suffix === 'physical-education-pool')
  ) {
    return 'dedicated_bucket_credits'
  }
  if (suffix === 'free-elective-pool') return 'none'
  if (suffix.includes('additional')) return 'shared_bucket_credits'
  if (pool.linkedCreditBucketId && bucketSharers.length > 1) {
    return 'shared_bucket_credits'
  }
  return 'none'
}

export function resolvePoolProgressDisplay(
  pool: ElectiveBucket,
  allPools: ElectiveBucket[] = [],
): PoolProgressDisplay {
  if (pool.progressDisplay) {
    return pool.progressDisplay
  }
  return computePoolProgressDisplay(pool, allPools)
}

export function poolAllowedPrefixes(pool: ElectiveBucket): string[] {
  const prefixes = [...(pool.allowedPrefixes ?? []), ...(pool.rule.allowedPrefixes ?? [])]
  return [...new Set(prefixes.map((prefix) => String(prefix)))]
}

/** Whether a course number belongs to this pool's catalog list or prefix rules. */
export function courseMatchesPoolCatalog(courseNumber: string, pool: ElectiveBucket): boolean {
  const keys = new Set(courseNumberKeys(courseNumber))

  const matchesListedCourse = (course: ElectivePoolCourse): boolean => {
    for (const key of courseNumberKeys(course.courseNumber)) {
      if (keys.has(key)) return true
    }
    for (const alternative of course.alternatives ?? []) {
      for (const key of courseNumberKeys(alternative)) {
        if (keys.has(key)) return true
      }
    }
    return false
  }

  for (const course of pool.courses) {
    if (matchesListedCourse(course)) return true
  }

  const prefixes = poolAllowedPrefixes(pool)
  if (!prefixes.length) return false

  const canonical = canonicalCourseNumber(courseNumber)
  return prefixes.some(
    (prefix) =>
      canonical.startsWith(prefix) ||
      courseNumber.startsWith(prefix) ||
      [...keys].some((key) => key.startsWith(prefix)),
  )
}

function isExplicitSiblingPool(pool: ElectiveBucket): boolean {
  const operator = pool.rule.operator
  if (operator === 'choose_chain' || operator === 'choose_n') return true

  const suffix = groupSuffix(pool.groupId)
  return (
    suffix.includes('focus-chain') ||
    suffix.includes('behavior-science') ||
    suffix.includes('statistics-elective')
  )
}

function isSharedPrefixCatchAllPool(
  pool: ElectiveBucket,
  progressDisplay: PoolProgressDisplay,
): boolean {
  if (progressDisplay !== 'shared_bucket_credits') return false

  const suffix = groupSuffix(pool.groupId)
  return (
    suffix.includes('additional') ||
    (pool.rule.operator === 'min_credits' && poolAllowedPrefixes(pool).length > 0)
  )
}

function isCourseClaimedByExplicitSiblingPool(
  courseNumber: string,
  pool: ElectiveBucket,
  allPools: ElectiveBucket[],
): boolean {
  if (!pool.linkedCreditBucketId) return false

  return allPools.some((sibling) => {
    if (sibling.groupId === pool.groupId) return false
    if (sibling.linkedCreditBucketId !== pool.linkedCreditBucketId) return false
    if (!isExplicitSiblingPool(sibling)) return false
    return courseMatchesPoolCatalog(courseNumber, sibling)
  })
}

export function poolMatchedBucketCourses(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  allPools: ElectiveBucket[] = [],
) {
  const progressDisplay = resolvePoolProgressDisplay(pool, allPools)
  const bucketAssignsPools = (bucket.completedCourses ?? []).some(
    (course) => Boolean(course.assignedPoolGroupId),
  )

  if (progressDisplay === 'dedicated_bucket_credits') {
    return (bucket.completedCourses ?? []).filter((course) => {
      if (!course.courseNumber) return false
      if (course.assignedPoolGroupId) {
        return course.assignedPoolGroupId === pool.groupId
      }
      return courseMatchesPoolCatalog(course.courseNumber, pool)
    })
  }

  let matched = (bucket.completedCourses ?? []).filter((course) => {
    if (!course.courseNumber) return false
    if (course.assignedPoolGroupId) {
      return course.assignedPoolGroupId === pool.groupId
    }
    if (bucketAssignsPools) {
      return false
    }
    return courseMatchesPoolCatalog(course.courseNumber, pool)
  })

  if (isSharedPrefixCatchAllPool(pool, progressDisplay)) {
    matched = matched.filter(
      (course) =>
        course.courseNumber &&
        (course.assignedPoolGroupId === pool.groupId ||
          !isCourseClaimedByExplicitSiblingPool(course.courseNumber, pool, allPools)),
    )
  }

  if (pool.rule.operator === 'choose_n' && pool.rule.chooseCount && pool.rule.chooseCount > 0) {
    return [...matched]
      .sort((left, right) => (left.courseNumber ?? '').localeCompare(right.courseNumber ?? ''))
      .slice(0, pool.rule.chooseCount)
  }

  return matched
}

export function poolCreditsCompleted(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  allPools: ElectiveBucket[] = [],
): number {
  return poolMatchedBucketCourses(pool, bucket, allPools).reduce(
    (sum, course) => sum + (course.creditsEarned ?? 0),
    0,
  )
}

export type PoolCreditProgress = {
  displayCreditsCompleted: number
  bucketCreditsCompleted: number
  bucketMinCredits: number
}

export function resolvePoolCreditProgress(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  progressDisplay: PoolProgressDisplay,
  allPools: ElectiveBucket[] = [],
): PoolCreditProgress {
  const bucketCreditsCompleted = bucket.creditsCompleted ?? 0
  const bucketMinCredits = bucket.minCredits ?? 0
  const poolCredits = poolCreditsCompleted(pool, bucket, allPools)

  if (progressDisplay === 'dedicated_bucket_credits') {
    return {
      displayCreditsCompleted: bucketCreditsCompleted,
      bucketCreditsCompleted,
      bucketMinCredits,
    }
  }

  return {
    displayCreditsCompleted: poolCredits,
    bucketCreditsCompleted,
    bucketMinCredits,
  }
}

export function bucketCountedCourseNumbers(
  bucket: RequirementProgressEntry,
): Set<string> {
  const counted = new Set<string>()
  for (const course of bucket.completedCourses ?? []) {
    addCourseNumberKeys(counted, course.courseNumber)
  }
  return counted
}

export function poolCountedCourseNumbers(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  allPools: ElectiveBucket[] = [],
): Set<string> {
  const progressDisplay = resolvePoolProgressDisplay(pool, allPools)
  if (progressDisplay === 'dedicated_bucket_credits') {
    return bucketCountedCourseNumbers(bucket)
  }

  const counted = new Set<string>()
  for (const course of poolMatchedBucketCourses(pool, bucket, allPools)) {
    addCourseNumberKeys(counted, course.courseNumber)
  }
  return counted
}

export function chainStepPercent(counted: number, required: number | null | undefined): number {
  if (!required || required <= 0) return counted > 0 ? 100 : 0
  return Math.min(100, (counted / required) * 100)
}

export function poolProgressSummary(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  t?: (key: string) => string,
  allPools: ElectiveBucket[] = [],
  options?: {
    curriculumGraph?: CurriculumGraph | null
    graduationProgress?: GraduationProgress | null
    requiredCurriculumNumbers?: Set<string>
  },
): PoolProgressSummary {
  const progressDisplay = resolvePoolProgressDisplay(pool, allPools)
  const creditProgress = resolvePoolCreditProgress(pool, bucket, progressDisplay, allPools)
  const countedNumbers = poolCountedCourseNumbers(pool, bucket, allPools)
  const listed = dedupedPoolListedCount(pool, {
    countedNumbers,
    requiredCurriculumNumbers: options?.requiredCurriculumNumbers,
    curriculumGraph: options?.curriculumGraph,
    progress: options?.graduationProgress,
  })
  const counted =
    progressDisplay === 'dedicated_bucket_credits'
      ? (bucket.completedCourses ?? []).length
      : poolMatchedBucketCourses(pool, bucket, allPools).length

  let chainStepsRequired =
    pool.rule.operator === 'choose_chain'
      ? pool.rule.chooseCount ?? 3
      : pool.rule.operator === 'choose_n'
        ? pool.rule.chooseCount ?? 1
        : null
  let chainStepsCompleted = counted

  if (isFocusChainPool(pool) && t && hasStructuredChainLayout(pool)) {
    const equivalenceGroups = buildCourseEquivalenceGroups({
      curriculumGraph: options?.curriculumGraph,
      progress: options?.graduationProgress,
      poolCourses: pool.courses,
    })
    const expandedCounted = expandNumbersWithEquivalence(countedNumbers, equivalenceGroups)
    const view = buildChainRequirementView(pool, t, expandedCounted)
    if (view?.layout === 'steps') {
      chainStepsRequired = view.steps.length
      chainStepsCompleted = view.steps.filter((step) => step.satisfied).length
    } else if (view?.layout === 'pick_one_chain') {
      const best = [...view.chains].sort(
        (left, right) => right.satisfiedCount - left.satisfiedCount,
      )[0]
      chainStepsRequired = best?.steps.length ?? chainStepsRequired
      chainStepsCompleted = best?.satisfiedCount ?? 0
    }
  } else if (pool.rule.operator === 'choose_n' && chainStepsRequired != null) {
    chainStepsCompleted = Math.min(counted, chainStepsRequired)
  }

  const apiEvaluation = bucket.poolConstraints?.allPools?.find(
    (entry) => entry.requirementGroupId === pool.groupId,
  )
  if (apiEvaluation?.stepsRequired != null) {
    chainStepsRequired = apiEvaluation.stepsRequired
    chainStepsCompleted = apiEvaluation.stepsCompleted ?? 0
  }

  return {
    counted,
    listed,
    creditsCompleted: creditProgress.displayCreditsCompleted,
    bucketCreditsCompleted: creditProgress.bucketCreditsCompleted,
    chainStepsCompleted,
    chainStepsRequired,
  }
}

export function filterPoolCourses(
  courses: ElectivePoolCourse[],
  options: {
    query: string
    completedNumbers: Set<string>
    filter: PoolCourseFilter
  },
): ElectivePoolCourse[] {
  const normalizedQuery = options.query.trim().toLowerCase()

  return courses.filter((course) => {
    const isCounted = isCountedCourse(course.courseNumber, options.completedNumbers)
    if (options.filter === 'counted' && !isCounted) return false
    if (options.filter === 'remaining' && isCounted) return false

    if (!normalizedQuery) return true

    const haystack = [course.courseNumber, course.title ?? '', course.titleHe ?? '', ...(course.notes ?? [])]
      .join(' ')
      .toLowerCase()
    return haystack.includes(normalizedQuery)
  })
}

export function sortPoolCourses(
  courses: ElectivePoolCourse[],
  sort: PoolCourseSort,
  completedNumbers: Set<string>,
): ElectivePoolCourse[] {
  const sorted = [...courses]

  switch (sort) {
    case 'number':
      return sorted.sort((left, right) => left.courseNumber.localeCompare(right.courseNumber))
    case 'title':
      return sorted.sort((left, right) =>
        (left.title ?? left.courseNumber).localeCompare(right.title ?? right.courseNumber),
      )
    case 'credits':
      return sorted.sort((left, right) => (right.credits ?? 0) - (left.credits ?? 0))
    case 'counted_first':
      return sorted.sort((left, right) => {
        const leftRank = isCountedCourse(left.courseNumber, completedNumbers) ? 0 : 1
        const rightRank = isCountedCourse(right.courseNumber, completedNumbers) ? 0 : 1
        if (leftRank !== rightRank) return leftRank - rightRank
        return left.courseNumber.localeCompare(right.courseNumber)
      })
    default:
      return sorted
  }
}

export function preparePoolCourseView(
  courses: ElectivePoolCourse[],
  options: {
    query: string
    completedNumbers: Set<string>
    filter: PoolCourseFilter
    sort: PoolCourseSort
    curriculumGraph?: CurriculumGraph | null
    graduationProgress?: GraduationProgress | null
    requiredCurriculumNumbers?: Set<string>
  },
): ElectivePoolCourse[] {
  const deduped = dedupeEquivalentPoolCourses(courses, {
    countedNumbers: options.completedNumbers,
    requiredCurriculumNumbers: options.requiredCurriculumNumbers,
    curriculumGraph: options.curriculumGraph,
    progress: options.graduationProgress,
  })
  const groups = buildCourseEquivalenceGroups({
    curriculumGraph: options.curriculumGraph,
    progress: options.graduationProgress,
    poolCourses: courses,
  })
  const expandedCompleted = expandNumbersWithEquivalence(options.completedNumbers, groups)
  const filtered = filterPoolCourses(deduped, {
    ...options,
    completedNumbers: expandedCompleted,
  })
  return sortPoolCourses(filtered, options.sort, expandedCompleted)
}

export function countDedupedPoolCourses(
  courses: ElectivePoolCourse[],
  options: {
    countedNumbers: Set<string>
    requiredCurriculumNumbers?: Set<string>
    curriculumGraph?: CurriculumGraph | null
    progress?: GraduationProgress | null
  },
): number {
  return dedupeEquivalentPoolCourses(courses, options).length
}

export function dedupedPoolListedCount(
  pool: ElectiveBucket,
  options: {
    countedNumbers: Set<string>
    requiredCurriculumNumbers?: Set<string>
    curriculumGraph?: CurriculumGraph | null
    progress?: GraduationProgress | null
  },
): number {
  if (pool.courses.length === 0 && pool.courseCount != null) {
    return pool.courseCount
  }
  return countDedupedPoolCourses(pool.courses, options)
}

export function catalogSearchLink(query: string): string {
  const trimmed = query.trim()
  if (!trimmed) return '/catalog'
  return `/catalog?${new URLSearchParams({ q: trimmed }).toString()}`
}

export function catalogLinkForPool(pool: ElectiveBucket): string {
  const prefix = pool.allowedPrefixes?.[0]
  if (prefix) return catalogSearchLink(prefix)
  return '/catalog'
}

export const VIRTUAL_LIST_THRESHOLD = 48

export function groupSuffix(groupId: string): string {
  const separator = groupId.indexOf(':')
  return separator >= 0 ? groupId.slice(separator + 1) : groupId
}

export function localizedPoolTitle(
  pool: ElectiveBucket,
  t: (key: string) => string,
): string {
  const key = `progress.electiveExplorer.pools.${groupSuffix(pool.groupId)}`
  const translated = t(key)
  return translated !== key ? translated : pool.title ?? pool.groupId
}

export function localizedPoolDescriptions(
  pool: ElectiveBucket,
  t: (key: string) => string,
): string[] {
  const i18nKey = `progress.electiveExplorer.poolDescriptions.${groupSuffix(pool.groupId)}`
  const translated = t(i18nKey)
  if (translated !== i18nKey) {
    return translated
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
  }

  const lines: string[] = []
  if (pool.catalogDescription?.trim()) {
    lines.push(pool.catalogDescription.trim())
  }
  for (const note of pool.notes ?? []) {
    const text = String(note).trim()
    if (text && !lines.includes(text)) {
      lines.push(text)
    }
  }
  return lines
}

export function localizedBucketTitle(
  bucket: Pick<RequirementProgressEntry, 'requirementGroupId'> & { title?: string | null },
  t: (key: string) => string,
): string {
  const key = `progress.electiveExplorer.buckets.${groupSuffix(bucket.requirementGroupId)}`
  const translated = t(key)
  return translated !== key ? translated : bucket.title ?? bucket.requirementGroupId
}

export function localizedChainName(
  chain: string,
  t: (key: string) => string,
): string {
  const key = `progress.electiveExplorer.chains.${chain}`
  const translated = t(key)
  return translated !== key ? translated : chain.replace(/_/g, ' ')
}

export function localizedCourseTitle(
  course: ElectivePoolCourse,
  locale: 'he' | 'en',
): string {
  if (locale === 'he' && course.titleHe) return course.titleHe
  return course.title ?? course.courseNumber
}

export function isChainPool(pool: ElectiveBucket): boolean {
  return isFocusChainPool(pool) || pool.rule.operator === 'choose_n'
}

export function shouldShowPoolCatalogExplanation(pool: ElectiveBucket): boolean {
  return isChainPool(pool) || Boolean(pool.catalogDescription) || Boolean(pool.notes?.length)
}

export function poolCourseFilterCounts(
  courses: ElectivePoolCourse[],
  completedNumbers: Set<string>,
  options?: {
    curriculumGraph?: CurriculumGraph | null
    graduationProgress?: GraduationProgress | null
    requiredCurriculumNumbers?: Set<string>
  },
): Record<PoolCourseFilter, number> {
  const groups = buildCourseEquivalenceGroups({
    curriculumGraph: options?.curriculumGraph,
    progress: options?.graduationProgress,
    poolCourses: courses,
  })
  const expandedCompleted = expandNumbersWithEquivalence(completedNumbers, groups)
  const deduped = dedupeEquivalentPoolCourses(courses, {
    countedNumbers: completedNumbers,
    requiredCurriculumNumbers: options?.requiredCurriculumNumbers,
    curriculumGraph: options?.curriculumGraph,
    progress: options?.graduationProgress,
  })
  const counted = deduped.filter((course) =>
    isCountedViaEquivalence(course.courseNumber, expandedCompleted, groups),
  ).length
  return {
    all: deduped.length,
    counted,
    remaining: deduped.length - counted,
  }
}

export function categoryAccentClass(category: PoolCategory): string {
  switch (category) {
    case 'credit_pool':
      return 'border-s-teal-500'
    case 'focus_chain':
      return 'border-s-violet-500'
    case 'choose_n':
      return 'border-s-amber-500'
    case 'faculty_list':
      return 'border-s-sky-500'
    case 'general_elective':
      return 'border-s-emerald-500'
    default:
      return 'border-s-stone-400'
  }
}

export function categorySurfaceClass(category: PoolCategory): string {
  switch (category) {
    case 'credit_pool':
      return 'bg-teal-50 text-teal-700'
    case 'focus_chain':
      return 'bg-violet-50 text-violet-700'
    case 'choose_n':
      return 'bg-amber-50 text-amber-800'
    case 'faculty_list':
      return 'bg-sky-50 text-sky-700'
    case 'general_elective':
      return 'bg-emerald-50 text-emerald-800'
    default:
      return 'bg-stone-100 text-stone-700'
  }
}

export const POOL_COURSES_PAGE_SIZE = 40
