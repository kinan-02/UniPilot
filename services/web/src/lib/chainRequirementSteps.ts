import type { ElectiveBucket, ElectivePoolCourse } from '../types/api'
import { groupSuffix, isChainPool } from './electivePools'

export type ChainStepKind = 'required' | 'choose_one'

export type ChainStepListing = 'fixed' | 'remaining' | 'none'

export type ChainStepDefinition = {
  id: string
  labelKey: string
  kind: ChainStepKind
  listing?: ChainStepListing
  courseNumbers?: string[]
  noteKey?: string
}

export type ChainAlternativeDefinition = {
  id: string
  titleKey: string
  steps: ChainStepDefinition[]
}

export type PoolChainLayout =
  | { type: 'steps'; steps: ChainStepDefinition[] }
  | { type: 'pick_one_chain'; chains: ChainAlternativeDefinition[] }

const DNE_STARRED_COURSE_NUMBERS = [
  '0960222',
  '0960231',
  '0960235',
  '0960262',
  '0960324',
  '0960693',
  '0970135',
  '0970200',
  '0970215',
  '0970216',
  '0970222',
  '0970247',
  '0970248',
  '0970272',
  '0970400',
] as const

const POOL_CHAIN_LAYOUTS: Record<string, PoolChainLayout> = {
  'is-behavior-science-chain': {
    type: 'steps',
    steps: [
      {
        id: 'behavior',
        labelKey: 'progress.electiveExplorer.chainStepLabels.behaviorScience',
        kind: 'choose_one',
        courseNumbers: ['0960600', '0960620'],
      },
    ],
  },
  'is-focus-chain-performance': {
    type: 'steps',
    steps: [
      {
        id: 'p1',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part1Required',
        kind: 'required',
        courseNumbers: ['0960327'],
      },
      {
        id: 'p2',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part2Required',
        kind: 'required',
        courseNumbers: ['0960324', '0980413'],
        noteKey: 'progress.electiveExplorer.chainStepNotes.substitute0980413',
      },
      {
        id: 'p3',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part3ChooseOne',
        kind: 'choose_one',
        courseNumbers: [
          '0960311',
          '0960335',
          '0960351',
          '0970135',
          '0970280',
          '0970325',
          '0970334',
        ],
      },
    ],
  },
  'is-focus-chain-ml': {
    type: 'steps',
    steps: [
      {
        id: 'p1',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part1Required',
        kind: 'required',
        courseNumbers: ['0970209'],
      },
      {
        id: 'p2',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part2ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0960212', '0960327', '0970414'],
      },
      {
        id: 'p3',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part3DneStarred',
        kind: 'choose_one',
        courseNumbers: [...DNE_STARRED_COURSE_NUMBERS],
        noteKey: 'progress.electiveExplorer.chainStepNotes.dneStarredElective',
      },
    ],
  },
  'is-focus-chain-game-theory': {
    type: 'steps',
    steps: [
      {
        id: 'p1',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part1ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0960226', '0960578', '0970317'],
      },
      {
        id: 'p2',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part2ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0960606', '0960617', '0960690'],
      },
      {
        id: 'p3',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part3FromPrior',
        kind: 'choose_one',
        courseNumbers: [
          '0960226',
          '0960578',
          '0970317',
          '0960606',
          '0960617',
          '0960690',
        ],
      },
    ],
  },
  'ie-statistics-elective-chain': {
    type: 'steps',
    steps: [
      {
        id: 'statistics',
        labelKey: 'progress.electiveExplorer.chainStepLabels.statisticsChooseOne',
        kind: 'choose_one',
        listing: 'remaining',
      },
    ],
  },
  'ie-behavior-science-chain': {
    type: 'steps',
    steps: [
      {
        id: 'behavior',
        labelKey: 'progress.electiveExplorer.chainStepLabels.behaviorScience',
        kind: 'choose_one',
        listing: 'remaining',
      },
    ],
  },
  'ie-focus-chain-game-theory': {
    type: 'steps',
    steps: [
      {
        id: 'p1',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part1ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0960226', '0960570', '0960578', '0970317'],
      },
      {
        id: 'p2',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part2ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0960606', '0960617', '0960690'],
      },
      {
        id: 'p3',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part3Or0211',
        kind: 'choose_one',
        courseNumbers: [
          '0960226',
          '0960570',
          '0960578',
          '0970317',
          '0960606',
          '0960617',
          '0960690',
          '0960211',
        ],
        noteKey: 'progress.electiveExplorer.chainStepNotes.part3FromPart1Or2',
      },
    ],
  },
  'ie-focus-chain-advanced-industry': {
    type: 'steps',
    steps: [
      {
        id: 'p1',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part1Required',
        kind: 'required',
        courseNumbers: ['0960411'],
      },
      {
        id: 'p2',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part2ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0940222', '0950111', '0960210', '0970247'],
      },
      {
        id: 'p3',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part3ChooseOne',
        kind: 'choose_one',
        courseNumbers: [
          '0940222',
          '0950111',
          '0960210',
          '0970247',
          '0960208',
          '0960266',
          '0960625',
          '0970139',
          '0960135',
          '0970244',
        ],
        noteKey: 'progress.electiveExplorer.chainStepNotes.part3FromPart2OrList',
      },
    ],
  },
  'ie-focus-chain-operations-research': {
    type: 'steps',
    steps: [
      {
        id: 'p1',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part1Required',
        kind: 'required',
        courseNumbers: ['0960327'],
      },
      {
        id: 'p2',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part2Required',
        kind: 'required',
        courseNumbers: ['0960570', '0980413'],
        noteKey: 'progress.electiveExplorer.chainStepNotes.substitute0980413',
      },
      {
        id: 'p3',
        labelKey: 'progress.electiveExplorer.chainStepLabels.part3ChooseOne',
        kind: 'choose_one',
        courseNumbers: ['0960311', '0960335'],
      },
    ],
  },
}

export function resolvePoolChainLayout(pool: ElectiveBucket): PoolChainLayout | null {
  const layout = POOL_CHAIN_LAYOUTS[groupSuffix(pool.groupId)]
  if (layout) return layout

  if (!isChainPool(pool)) return null

  return {
    type: 'steps',
    steps: [
      {
        id: 'choose',
        labelKey: 'progress.electiveExplorer.chainStepLabels.defaultChoose',
        kind: 'choose_one',
        listing: 'remaining',
      },
    ],
  }
}

export type ResolvedChainStep = {
  id: string
  stepNumber: number
  title: string
  kindLabel: string
  note?: string
  courses: ElectivePoolCourse[]
  satisfied: boolean
}

export type ResolvedChainAlternative = {
  id: string
  title: string
  steps: ResolvedChainStep[]
  satisfiedCount: number
}

export type ResolvedChainRequirementView =
  | { layout: 'steps'; steps: ResolvedChainStep[] }
  | { layout: 'pick_one_chain'; intro: string; chains: ResolvedChainAlternative[] }

/** Normalize Technion course numbers to 8-digit 0-prefixed strings (matches API catalog). */
function normalizeNumber(value: string): string {
  const digits = value.replace(/\D/g, '')
  if (digits.length < 7 || digits.length > 9) {
    return value.trim()
  }
  return digits.padStart(8, '0').slice(-8)
}

function courseIndex(pool: ElectiveBucket): Map<string, ElectivePoolCourse> {
  const index = new Map<string, ElectivePoolCourse>()
  for (const course of pool.courses) {
    const canonical = normalizeNumber(course.courseNumber)
    index.set(canonical, course)
    index.set(course.courseNumber, course)
  }
  return index
}

function coursesForStep(
  definition: ChainStepDefinition,
  pool: ElectiveBucket,
  index: Map<string, ElectivePoolCourse>,
  reservedNumbers: Set<string>,
): ElectivePoolCourse[] {
  const listing = definition.listing ?? (definition.courseNumbers ? 'fixed' : 'remaining')

  if (listing === 'none') {
    return []
  }

  if (listing === 'remaining') {
    return pool.courses.filter((course) => !reservedNumbers.has(course.courseNumber))
  }

  const courses: ElectivePoolCourse[] = []
  const seen = new Set<string>()
  for (const number of definition.courseNumbers ?? []) {
    const course = index.get(normalizeNumber(number)) ?? index.get(number)
    if (course && !seen.has(course.courseNumber)) {
      seen.add(course.courseNumber)
      courses.push(course)
    }
  }
  return courses
}

function stepSatisfied(courses: ElectivePoolCourse[], countedNumbers: Set<string>): boolean {
  return courses.some(
    (course) =>
      countedNumbers.has(course.courseNumber) ||
      countedNumbers.has(normalizeNumber(course.courseNumber)),
  )
}

function resolveSteps(
  definitions: ChainStepDefinition[],
  pool: ElectiveBucket,
  t: (key: string) => string,
  countedNumbers: Set<string>,
): ResolvedChainStep[] {
  const index = courseIndex(pool)
  const reserved = new Set<string>()
  const resolved: ResolvedChainStep[] = []

  for (const [offset, definition] of definitions.entries()) {
    const courses = coursesForStep(definition, pool, index, reserved)
    for (const course of courses) {
      reserved.add(course.courseNumber)
    }

    const titleKey = definition.labelKey
    const title = t(titleKey) !== titleKey ? t(titleKey) : definition.id
    const kindKey =
      definition.kind === 'required'
        ? 'progress.electiveExplorer.chainStepKinds.required'
        : 'progress.electiveExplorer.chainStepKinds.chooseOne'
    const kindLabel = t(kindKey)
    const noteKey = definition.noteKey
    const note = noteKey && t(noteKey) !== noteKey ? t(noteKey) : undefined

    resolved.push({
      id: definition.id,
      stepNumber: offset + 1,
      title,
      kindLabel,
      note,
      courses,
      satisfied: stepSatisfied(courses, countedNumbers),
    })
  }

  return resolved
}

export function buildChainRequirementView(
  pool: ElectiveBucket,
  t: (key: string) => string,
  countedNumbers: Set<string>,
): ResolvedChainRequirementView | null {
  const layout = resolvePoolChainLayout(pool)
  if (!layout) return null

  if (layout.type === 'steps') {
    return {
      layout: 'steps',
      steps: resolveSteps(layout.steps, pool, t, countedNumbers),
    }
  }

  const introKey = 'progress.electiveExplorer.pickOneChainIntro'
  const intro = t(introKey) !== introKey ? t(introKey) : ''

  return {
    layout: 'pick_one_chain',
    intro,
    chains: layout.chains.map((chain) => {
      const steps = resolveSteps(chain.steps, pool, t, countedNumbers)
      return {
        id: chain.id,
        title: t(chain.titleKey) !== chain.titleKey ? t(chain.titleKey) : chain.id,
        steps,
        satisfiedCount: steps.filter((step) => step.satisfied).length,
      }
    }),
  }
}

export function hasStructuredChainLayout(pool: ElectiveBucket): boolean {
  return resolvePoolChainLayout(pool) !== null
}
