import { describe, expect, it } from 'vitest'
import {
  buildChainRequirementView,
  hasStructuredChainLayout,
  resolvePoolChainLayout,
} from './chainRequirementSteps'
import type { ElectiveBucket } from '../types/api'

const t = (key: string) =>
  key.startsWith('progress.electiveExplorer.chainStepNotes.')
    ? `translated:${key}`
    : key

function chainPool(groupId: string, courses: { courseNumber: string; title: string }[]): ElectiveBucket {
  return {
    groupId,
    title: groupId,
    rule: { type: 'choose_chain' },
    courses: courses.map((course) => ({
      courseNumber: course.courseNumber,
      title: course.title,
      credits: 3,
    })),
    courseCount: courses.length,
    linkedCreditBucketId: 'elective-faculty',
  }
}

describe('chainRequirementSteps', () => {
  it('resolves IS performance focus chain into three parts', () => {
    const pool = chainPool('track-information-systems-engineering:is-focus-chain-performance', [
      { courseNumber: '00960327', title: 'Nonlinear OR' },
      { courseNumber: '00960324', title: 'Service systems' },
      { courseNumber: '00960311', title: 'Elective A' },
      { courseNumber: '00970334', title: 'Elective B' },
    ])

    const layout = resolvePoolChainLayout(pool)
    expect(layout?.type).toBe('steps')
    if (layout?.type !== 'steps') return

    expect(layout.steps).toHaveLength(3)

    const view = buildChainRequirementView(pool, t, new Set(['00960327']))
    expect(view?.layout).toBe('steps')
    if (view?.layout !== 'steps') return

    expect(view.steps).toHaveLength(3)
    expect(view.steps[0]?.courses).toHaveLength(1)
    expect(view.steps[0]?.satisfied).toBe(true)
    expect(view.steps[2]?.courses.map((c) => c.courseNumber)).toEqual(['00960311', '00970334'])
  })

  it('resolves IE game theory focus chain into three parts', () => {
    const pool = chainPool('track-industrial-engineering:ie-focus-chain-game-theory', [
      { courseNumber: '0960226', title: 'GT 1' },
      { courseNumber: '0960606', title: 'Behavioral econ' },
      { courseNumber: '0960211', title: 'Commerce' },
    ])

    const view = buildChainRequirementView(pool, t, new Set())
    expect(view?.layout).toBe('steps')
    if (view?.layout !== 'steps') return

    expect(view.steps).toHaveLength(3)
    expect(view.steps[2]?.courses.map((c) => c.courseNumber)).toEqual([
      '0960226',
      '0960606',
      '0960211',
    ])
  })

  it('lists DNE starred courses in ML part 3 when present in pool', () => {
    const pool = chainPool('track-information-systems-engineering:is-focus-chain-ml', [
      { courseNumber: '0970209', title: 'CL2' },
      { courseNumber: '0960212', title: 'ML elective' },
      { courseNumber: '0970215', title: 'NLP starred' },
      { courseNumber: '0999999', title: 'Should not appear in part 3' },
    ])

    const view = buildChainRequirementView(pool, t, new Set())
    if (view?.layout !== 'steps') return

    const part3 = view.steps[2]
    expect(part3?.courses.map((c) => c.courseNumber)).toEqual(['0970215'])
    expect(part3?.note).toBe('translated:progress.electiveExplorer.chainStepNotes.dneStarredElective')
  })

  it('matches 7-digit step definitions against 8-digit catalog course numbers', () => {
    const pool = chainPool('track-information-systems-engineering:is-behavior-science-chain', [
      { courseNumber: '00960600', title: 'Behavior A' },
      { courseNumber: '00960620', title: 'Behavior B' },
    ])
    const view = buildChainRequirementView(pool, t, new Set())
    if (view?.layout !== 'steps') return
    expect(view.steps[0]?.courses).toHaveLength(2)
  })

  it('detects structured layout for chain pools', () => {
    const pool = chainPool('track-information-systems-engineering:is-behavior-science-chain', [
      { courseNumber: '0960600', title: 'Behavior A' },
    ])
    expect(hasStructuredChainLayout(pool)).toBe(true)
  })
})
