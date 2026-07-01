import { describe, expect, it } from 'vitest'
import {
  buildCourseEquivalenceGroups,
  catalogOverlapEquivalenceGroupsFromGraph,
  catalogOverlapEquivalenceGroupsFromSources,
  crossTrackEquivalenceGroupsFromGraph,
  dedupeEquivalentPoolCourses,
  isCountedViaEquivalence,
  knownCrossTrackEquivalenceGroups,
} from './courseEquivalence'

describe('courseEquivalence', () => {
  it('treats ISE and DNE e-commerce codes as one equivalence group', () => {
    const groups = knownCrossTrackEquivalenceGroups()
    expect(groups).toHaveLength(1)
    expect([...groups[0]!]).toEqual(
      expect.arrayContaining(['00960211', '00960221']),
    )
  })

  it('counts one cross-track code when the other is on the transcript', () => {
    const groups = knownCrossTrackEquivalenceGroups()
    const counted = new Set(['00960211'])
    expect(isCountedViaEquivalence('00960221', counted, groups)).toBe(true)
    expect(isCountedViaEquivalence('00960327', counted, groups)).toBe(false)
  })

  it('reads cross-track groups from curriculum graph API payload', () => {
    const fromGraph = crossTrackEquivalenceGroupsFromGraph({
      crossTrackEquivalenceGroups: [['00960327', '00960328']],
    })
    expect([...fromGraph[0]!]).toEqual(expect.arrayContaining(['00960327', '00960328']))

    const fallback = crossTrackEquivalenceGroupsFromGraph({})
    expect([...fallback[0]!]).toEqual(expect.arrayContaining(['00960211', '00960221']))
  })

  it('reads catalog overlap groups from curriculum graph API payload', () => {
    const fromGraph = catalogOverlapEquivalenceGroupsFromGraph({
      catalogOverlapEquivalenceGroups: [['02340114', '02340117']],
    })
    expect([...fromGraph[0]!]).toEqual(expect.arrayContaining(['02340114', '02340117']))

    const groups = buildCourseEquivalenceGroups({
      curriculumGraph: {
        catalogOverlapEquivalenceGroups: [['02340114', '02340117']],
      },
    })
    expect(isCountedViaEquivalence('02340117', new Set(['02340114']), groups)).toBe(true)
  })

  it('reads catalog overlap groups from progress payload when graph is absent', () => {
    const fromProgress = catalogOverlapEquivalenceGroupsFromSources({
      progress: {
        catalogOverlapEquivalenceGroups: [['02340114', '02340117']],
      } as import('../types/api').GraduationProgress,
    })
    expect([...fromProgress[0]!]).toEqual(expect.arrayContaining(['02340114', '02340117']))
  })

  it('shows only the completed code when duplicate cross-track entries exist in a pool', () => {
    const courses = [
      { courseNumber: '00960221', title: 'E-commerce models' },
      { courseNumber: '00960211', title: 'E-commerce models', credits: 3.5 },
      { courseNumber: '00960327', title: 'Other course' },
    ]
    const deduped = dedupeEquivalentPoolCourses(courses, {
      countedNumbers: new Set(['00960211']),
      requiredCurriculumNumbers: new Set(['00960221']),
    })
    expect(deduped.map((course) => course.courseNumber)).toEqual(['00960211', '00960327'])
  })
})
