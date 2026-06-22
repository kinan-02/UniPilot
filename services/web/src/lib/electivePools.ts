import type {
  CurriculumGraph,
  ElectiveBucket,
  ElectivePoolCourse,
  GraduationProgress,
  RequirementProgressEntry,
} from '../types/api'

export type PoolCategory = 'credit_pool' | 'focus_chain' | 'choose_n' | 'faculty_list' | 'other'

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

export function groupPoolsByCategory(
  pools: ElectiveBucket[],
): Array<{ category: PoolCategory; pools: ElectiveBucket[] }> {
  const order: PoolCategory[] = ['credit_pool', 'focus_chain', 'choose_n', 'faculty_list', 'other']
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
  return new Set(
    (bucket.completedCourses ?? [])
      .map((course) => course.courseNumber)
      .filter((value): value is string => Boolean(value)),
  )
}

export function buildTranscriptCourseNumbers(
  requirementProgress: RequirementProgressEntry[] | undefined,
): Set<string> {
  const numbers = new Set<string>()
  for (const bucket of requirementProgress ?? []) {
    for (const course of bucket.completedCourses ?? []) {
      if (course.courseNumber) numbers.add(course.courseNumber)
    }
  }
  return numbers
}

export function buildRequiredCurriculumCourseNumbers(
  requirementProgress: RequirementProgressEntry[] | undefined,
  options?: {
    curriculumGraph?: CurriculumGraph | null
    remainingMandatory?: GraduationProgress['remainingMandatoryCourses']
  },
): Set<string> {
  const numbers = new Set<string>()
  for (const bucket of requirementProgress ?? []) {
    if (bucket.isMandatory === false) continue
    for (const course of bucket.completedCourses ?? []) {
      if (course.courseNumber) numbers.add(course.courseNumber)
    }
  }
  for (const course of options?.remainingMandatory ?? []) {
    if (course.courseNumber) numbers.add(course.courseNumber)
  }
  for (const node of options?.curriculumGraph?.nodes ?? []) {
    if (node.courseNumber) numbers.add(node.courseNumber)
  }
  return numbers
}

export function resolvePoolProgressDisplay(
  pool: ElectiveBucket,
  allPools: ElectiveBucket[] = [],
): PoolProgressDisplay {
  if (pool.progressDisplay) return pool.progressDisplay

  if (isChainPool(pool)) return 'chain_steps'
  const suffix = groupSuffix(pool.groupId)
  if (suffix === 'elective-ds-pool' || suffix === 'elective-faculty-pool') {
    return 'dedicated_bucket_credits'
  }
  if (suffix.includes('additional')) return 'shared_bucket_credits'
  const linkedId = pool.linkedCreditBucketId
  if (linkedId) {
    const sharers = allPools.filter((entry) => entry.linkedCreditBucketId === linkedId)
    if (sharers.length > 1) return 'none'
  }
  return 'none'
}

export function poolCountedCourseNumbers(
  pool: ElectiveBucket,
  bucket: RequirementProgressEntry,
  transcriptNumbers: Set<string>,
): Set<string> {
  const poolNumbers = new Set(pool.courses.map((course) => course.courseNumber))
  const fromBucket = completedCourseNumberSet(bucket)
  const counted = new Set<string>()
  for (const number of poolNumbers) {
    if (fromBucket.has(number) || transcriptNumbers.has(number)) {
      counted.add(number)
    }
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
  transcriptNumbers?: Set<string>,
): PoolProgressSummary {
  const countedNumbers = transcriptNumbers
    ? poolCountedCourseNumbers(pool, bucket, transcriptNumbers)
    : completedCourseNumberSet(bucket)
  const listed = pool.courses.length
  const counted = pool.courses.filter((course) => countedNumbers.has(course.courseNumber)).length
  const chainStepsRequired =
    pool.rule.operator === 'choose_chain'
      ? pool.rule.chooseCount ?? 3
      : pool.rule.operator === 'choose_n'
        ? pool.rule.chooseCount ?? 1
        : null

  return {
    counted,
    listed,
    chainStepsCompleted: counted,
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
    const isCounted = options.completedNumbers.has(course.courseNumber)
    if (options.filter === 'counted' && !isCounted) return false
    if (options.filter === 'remaining' && isCounted) return false

    if (!normalizedQuery) return true

    const haystack = [course.courseNumber, course.title ?? '', ...(course.notes ?? [])]
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
        const leftRank = completedNumbers.has(left.courseNumber) ? 0 : 1
        const rightRank = completedNumbers.has(right.courseNumber) ? 0 : 1
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
  },
): ElectivePoolCourse[] {
  const filtered = filterPoolCourses(courses, options)
  return sortPoolCourses(filtered, options.sort, options.completedNumbers)
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
  return pool.rule.operator === 'choose_chain' || pool.rule.operator === 'choose_n'
}

export function shouldShowPoolCatalogExplanation(pool: ElectiveBucket): boolean {
  return isChainPool(pool) || Boolean(pool.catalogDescription) || Boolean(pool.notes?.length)
}

export function poolCourseFilterCounts(
  courses: ElectivePoolCourse[],
  completedNumbers: Set<string>,
): Record<PoolCourseFilter, number> {
  const counted = courses.filter((course) => completedNumbers.has(course.courseNumber)).length
  return {
    all: courses.length,
    counted,
    remaining: courses.length - counted,
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
    default:
      return 'bg-stone-100 text-stone-700'
  }
}

export const POOL_COURSES_PAGE_SIZE = 40
