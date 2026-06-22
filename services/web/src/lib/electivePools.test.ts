import { describe, expect, it } from 'vitest'
import {
  catalogSearchLink,
  classifyPool,
  filterPoolCourses,
  findPoolForBucket,
  findPoolsForBucket,
  groupPoolsByCategory,
  interpolateTemplate,
  poolCourseFilterCounts,
  localizedPoolDescriptions,
  poolProgressSummary,
  preparePoolCourseView,
  resolvePoolProgressDisplay,
  ruleOperatorTranslationKey,
  sortPoolCourses,
} from './electivePools'
import type { ElectiveBucket, RequirementProgressEntry } from '../types/api'

const bucket = (overrides: Partial<RequirementProgressEntry> = {}): RequirementProgressEntry => ({
  requirementGroupId: '009216-1-000:elective-ds',
  title: 'DS electives',
  isMandatory: true,
  status: 'in_progress',
  minCredits: 24.5,
  creditsCompleted: 3.5,
  creditsRemaining: 21,
  ...overrides,
})

const pool = (overrides: Partial<ElectiveBucket> = {}): ElectiveBucket => ({
  groupId: '009216-1-000:elective-ds-pool',
  title: 'DS pool',
  rule: { type: 'course_pool', operator: 'choose_credits' },
  courses: [],
  courseCount: 0,
  linkedCreditBucketId: '009216-1-000:elective-ds',
  explorerReady: true,
  ...overrides,
})

describe('findPoolsForBucket', () => {
  it('links via linkedCreditBucketId', () => {
    const result = findPoolsForBucket(bucket(), [pool()])
    expect(result[0]?.groupId).toBe('009216-1-000:elective-ds-pool')
  })

  it('returns multiple pools for the same credit bucket', () => {
    const result = findPoolsForBucket(bucket(), [
      pool(),
      pool({
        groupId: '009216-1-000:elective-ds-alt',
        linkedCreditBucketId: '009216-1-000:elective-ds',
      }),
    ])
    expect(result).toHaveLength(2)
  })

  it('skips pools that are not explorer ready', () => {
    const result = findPoolForBucket(bucket(), [pool({ explorerReady: false })])
    expect(result).toBeUndefined()
  })
})

describe('classifyPool', () => {
  it('classifies focus chains', () => {
    expect(
      classifyPool(pool({ rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 } })),
    ).toBe('focus_chain')
  })
})

describe('groupPoolsByCategory', () => {
  it('groups explorer-ready pools by category', () => {
    const groups = groupPoolsByCategory([
      pool(),
      pool({
        groupId: '009118-1-000:is-focus-chain-ml',
        rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      }),
    ])
    expect(groups.map((group) => group.category)).toEqual(['credit_pool', 'focus_chain'])
  })
})

describe('filterPoolCourses', () => {
  it('filters counted courses only', () => {
    const courses = filterPoolCourses(
      [
        { courseNumber: '00940345', title: 'Discrete math' },
        { courseNumber: '00940411', title: 'Data science intro' },
      ],
      {
        query: '',
        completedNumbers: new Set(['00940345']),
        filter: 'counted',
      },
    )
    expect(courses).toHaveLength(1)
    expect(courses[0]?.courseNumber).toBe('00940345')
  })
})

describe('localizedPoolDescriptions', () => {
  const t = (key: string) => {
    if (key === 'progress.electiveExplorer.poolDescriptions.is-focus-chain-ml') {
      return 'Part 1: 0970209\nPart 2: choose one option'
    }
    return key
  }

  it('prefers localized catalog text over API notes', () => {
    const lines = localizedPoolDescriptions(
      pool({
        groupId: '009118-1-000:is-focus-chain-ml',
        notes: ['English-only export note'],
      }),
      t,
    )
    expect(lines[0]).toContain('0970209')
    expect(lines).toHaveLength(2)
  })

  it('falls back to API notes when no i18n entry exists', () => {
    const lines = localizedPoolDescriptions(
      pool({
        groupId: '009118-1-000:custom-pool',
        notes: ['Advisor approval required'],
      }),
      (key) => key,
    )
    expect(lines).toEqual(['Advisor approval required'])
  })
})

describe('resolvePoolProgressDisplay', () => {
  it('shows chain steps for choose_n pools sharing a faculty bucket', () => {
    const pools = [
      pool({
        groupId: '009118-1-000:is-behavior-science-chain',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        rule: { type: 'course_pool', operator: 'choose_n', chooseCount: 1 },
      }),
      pool({
        groupId: '009118-1-000:is-additional-faculty-electives',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        rule: { type: 'course_pool', operator: 'min_credits' },
      }),
    ]
    expect(resolvePoolProgressDisplay(pools[0]!, pools)).toBe('chain_steps')
    expect(resolvePoolProgressDisplay(pools[1]!, pools)).toBe('shared_bucket_credits')
  })
})

describe('poolProgressSummary', () => {
  it('reports chain progress for choose_chain pools', () => {
    const summary = poolProgressSummary(
      pool({
        rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
        courses: [
          { courseNumber: 'A', title: 'A' },
          { courseNumber: 'B', title: 'B' },
        ],
      }),
      bucket({
        completedCourses: [{ courseId: '1', courseNumber: 'A', creditsEarned: 3 }],
      }),
    )
    expect(summary.chainStepsRequired).toBe(3)
    expect(summary.chainStepsCompleted).toBe(1)
  })
})

describe('ruleOperatorTranslationKey', () => {
  it('maps choose_chain operator', () => {
    expect(ruleOperatorTranslationKey('choose_chain')).toBe(
      'progress.electiveExplorer.ruleChooseChain',
    )
  })
})

describe('sortPoolCourses', () => {
  it('puts counted courses first when requested', () => {
    const courses = sortPoolCourses(
      [
        { courseNumber: '00940411', title: 'B' },
        { courseNumber: '00940345', title: 'A' },
      ],
      'counted_first',
      new Set(['00940411']),
    )
    expect(courses.map((course) => course.courseNumber)).toEqual(['00940411', '00940345'])
  })
})

describe('preparePoolCourseView', () => {
  it('filters then sorts courses', () => {
    const courses = preparePoolCourseView(
      [
        { courseNumber: '00940411', title: 'B', credits: 3 },
        { courseNumber: '00940345', title: 'A', credits: 5 },
      ],
      {
        query: '00940345',
        completedNumbers: new Set(),
        filter: 'all',
        sort: 'credits',
      },
    )
    expect(courses).toHaveLength(1)
    expect(courses[0]?.courseNumber).toBe('00940345')
  })
})

describe('catalogSearchLink', () => {
  it('builds catalog query links', () => {
    expect(catalogSearchLink('00940345')).toBe('/catalog?q=00940345')
    expect(catalogSearchLink('')).toBe('/catalog')
  })
})

describe('poolCourseFilterCounts', () => {
  it('counts all, counted, and remaining courses', () => {
    const counts = poolCourseFilterCounts(
      [
        { courseNumber: '00940345', title: 'A' },
        { courseNumber: '00940411', title: 'B' },
      ],
      new Set(['00940345']),
    )
    expect(counts).toEqual({ all: 2, counted: 1, remaining: 1 })
  })
})

describe('interpolateTemplate', () => {
  it('replaces placeholders', () => {
    expect(interpolateTemplate('{counted} of {listed}', { counted: 2, listed: 5 })).toBe('2 of 5')
  })
})
