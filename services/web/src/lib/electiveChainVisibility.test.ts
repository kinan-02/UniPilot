import { describe, expect, it } from 'vitest'
import {
  exclusiveChainGroupKey,
  filterPoolsByExclusiveChainSelection,
  resolveActiveExclusiveChainPool,
} from './electiveChainVisibility'
import type { ElectiveBucket, RequirementProgressEntry } from '../types/api'

const t = (key: string) => key

function focusChainPool(suffix: string, courses: string[]): ElectiveBucket {
  return {
    groupId: `009118-1-000:${suffix}`,
    title: suffix,
    rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
    courses: courses.map((courseNumber) => ({
      courseNumber,
      title: courseNumber,
      credits: 3.5,
    })),
    courseCount: courses.length,
    linkedCreditBucketId: '009118-1-000:elective-faculty',
    explorerReady: true,
  }
}

function facultyBucket(
  completedCourses: Array<{ courseNumber: string; creditsEarned?: number }> = [],
): RequirementProgressEntry {
  return {
    requirementGroupId: '009118-1-000:elective-faculty',
    title: 'Faculty electives',
    status: 'in_progress',
    minCredits: 24.5,
    creditsCompleted: 7,
    creditsRemaining: 17.5,
    eligibilityEnforcement: 'strict_pool',
    completedCourses: completedCourses.map((course, index) => ({
      courseId: `course-${index}`,
      courseNumber: course.courseNumber,
      creditsEarned: course.creditsEarned ?? 3.5,
    })),
  }
}

describe('exclusiveChainGroupKey', () => {
  it('groups IS focus chains under one pick-one key', () => {
    const pool = focusChainPool('is-focus-chain-ml', ['0970209'])
    expect(exclusiveChainGroupKey(pool)).toBe('009118-1-000:focus-chain')
  })

  it('groups CS science chains under one pick-one key', () => {
    const pool: ElectiveBucket = {
      ...focusChainPool('cs-science-chain-biology', ['01340058']),
      groupId: '023023-1-000:cs-science-chain-biology',
    }
    expect(exclusiveChainGroupKey(pool)).toBe('023023-1-000:science-chain')
  })
})

describe('resolveActiveExclusiveChainPool', () => {
  it('returns null when no chain has transcript progress', () => {
    const group = [
      focusChainPool('is-focus-chain-performance', ['00960327']),
      focusChainPool('is-focus-chain-ml', ['0970209']),
      focusChainPool('is-focus-chain-game-theory', ['0960226']),
    ]
    expect(
      resolveActiveExclusiveChainPool(group, [facultyBucket()], new Set(), t),
    ).toBeNull()
  })

  it('selects active chain from transcript numbers before bucket assignment', () => {
    const group = [
      focusChainPool('is-focus-chain-performance', ['00960327', '00960324', '00960311']),
      focusChainPool('is-focus-chain-ml', ['0970209', '0960212', '0970215']),
    ]
    const active = resolveActiveExclusiveChainPool(
      group,
      [facultyBucket()],
      new Set(['0970209']),
      t,
    )
    expect(active?.groupId).toContain('is-focus-chain-ml')
  })

  it('selects the chain with the strongest step progress', () => {
    const group = [
      focusChainPool('is-focus-chain-performance', ['00960327', '00960324', '00960311']),
      focusChainPool('is-focus-chain-ml', ['0970209', '0960212', '0970215']),
      focusChainPool('is-focus-chain-game-theory', ['0960226', '0960606']),
    ]
    const active = resolveActiveExclusiveChainPool(
      group,
      [facultyBucket([{ courseNumber: '00960327' }, { courseNumber: '00960324' }])],
      new Set(),
      t,
    )
    expect(active?.groupId).toBe('009118-1-000:is-focus-chain-performance')
  })
})

describe('filterPoolsByExclusiveChainSelection', () => {
  it('hides unselected focus chains once a track has progress', () => {
    const pools = [
      focusChainPool('is-focus-chain-performance', ['00960327', '00960324', '00960311']),
      focusChainPool('is-focus-chain-ml', ['0970209', '0960212', '0970215']),
      focusChainPool('is-focus-chain-game-theory', ['0960226', '0960606']),
      focusChainPool('is-behavior-science-chain', ['00960600']),
    ]
    const result = filterPoolsByExclusiveChainSelection(
      pools,
      [facultyBucket([{ courseNumber: '0970209' }])],
      new Set(),
      t,
    )
    expect(result.pools.map((pool) => pool.groupId)).toEqual([
      '009118-1-000:is-focus-chain-ml',
      '009118-1-000:is-behavior-science-chain',
    ])
    expect(result.hiddenExclusiveChainCount).toBe(2)
  })

  it('shows all chains before a selection is made', () => {
    const pools = [
      focusChainPool('is-focus-chain-performance', ['00960327']),
      focusChainPool('is-focus-chain-ml', ['0970209']),
    ]
    const result = filterPoolsByExclusiveChainSelection(
      pools,
      [facultyBucket()],
      new Set(),
      t,
    )
    expect(result.pools).toHaveLength(2)
    expect(result.hiddenExclusiveChainCount).toBe(0)
  })
})
