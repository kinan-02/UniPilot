import { describe, expect, it } from 'vitest'
import {
  buildRequiredCurriculumCourseNumbers,
  buildTranscriptCourseNumbers,
  catalogSearchLink,
  classifyPool,
  filterPoolCourses,
  findPoolForBucket,
  findPoolsForBucket,
  groupPoolsByCategory,
  interpolateTemplate,
  isCountedCourse,
  isGeneralTechnionPool,
  isRequiredCurriculumCourse,
  localizedBucketTitle,
  localizedPoolDescriptions,
  localizedPoolTitle,
  partitionExplorerPools,
  poolCountedCourseNumbers,
  poolCourseFilterCounts,
  poolProgressSummary,
  preparePoolCourseView,
  courseMatchesPoolCatalog,
  poolCreditsCompleted,
  poolMatchedBucketCourses,
  resolvePoolCreditProgress,
  resolvePoolProgressDisplay,
  ruleBadgeTone,
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

describe('partitionExplorerPools', () => {
  it('separates general Technion pools below program pools in fixed order', () => {
    const { programPools, generalTechnionPools } = partitionExplorerPools([
      pool({ groupId: '009216-1-000:physical-education-pool', linkedCreditBucketId: '009216-1-000:physical-education' }),
      pool(),
      pool({ groupId: '009216-1-000:free-elective-pool', linkedCreditBucketId: '009216-1-000:free-elective' }),
      pool({ groupId: '009216-1-000:enrichment-pool', linkedCreditBucketId: '009216-1-000:enrichment' }),
    ])
    expect(programPools.map((entry) => entry.groupId)).toEqual(['009216-1-000:elective-ds-pool'])
    expect(generalTechnionPools.map((entry) => entry.groupId)).toEqual([
      '009216-1-000:enrichment-pool',
      '009216-1-000:free-elective-pool',
      '009216-1-000:physical-education-pool',
    ])
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
  it('shows chain steps for choose_n pools (matches API progressDisplay)', () => {
    const pools = [
      pool({
        groupId: '009118-1-000:is-behavior-science-chain',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        rule: { type: 'course_pool', operator: 'choose_n', chooseCount: 1 },
      }),
      pool({
        groupId: '009118-1-000:is-additional-faculty-electives',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        rule: { type: 'course_pool', operator: 'min_credits', allowedPrefixes: ['094'] },
      }),
    ]
    expect(resolvePoolProgressDisplay(pools[0]!, pools)).toBe('chain_steps')
    expect(resolvePoolProgressDisplay(pools[1]!, pools)).toBe('shared_bucket_credits')
  })

  it('shows chain steps only for choose_chain focus pools', () => {
    expect(
      resolvePoolProgressDisplay(
        pool({
          groupId: '009118-1-000:is-focus-chain-ml',
          linkedCreditBucketId: '009118-1-000:elective-faculty',
          rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
        }),
        [],
      ),
    ).toBe('chain_steps')
  })

  it('uses shared credits when multiple pools share a faculty bucket', () => {
    const facultyPool = pool({
      groupId: '009118-1-000:elective-faculty-pool',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
    })
    const focusPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
    })
    const allPools = [facultyPool, focusPool]
    expect(resolvePoolProgressDisplay(facultyPool, allPools)).toBe('shared_bucket_credits')
    expect(resolvePoolProgressDisplay(focusPool, allPools)).toBe('chain_steps')
  })
})

describe('poolCountedCourseNumbers', () => {
  it('counts only courses assigned to the linked bucket', () => {
    const counted = poolCountedCourseNumbers(
      pool({
        groupId: '009118-1-000:elective-faculty-pool',
        courses: [
          { courseNumber: '00940411', title: 'Faculty course' },
          { courseNumber: '00960327', title: 'Focus course' },
        ],
      }),
      bucket({
        requirementGroupId: '009118-1-000:elective-faculty',
        eligibilityEnforcement: 'strict_pool',
        completedCourses: [{ courseId: '1', courseNumber: '00940411', creditsEarned: 3.5 }],
      }),
    )
    expect([...counted]).toContain('00940411')
    expect([...counted]).not.toContain('00960327')
  })

  it('marks all bucket courses counted for dedicated faculty pool display', () => {
    const facultyPool = pool({
      groupId: '009118-1-000:elective-faculty-pool',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      allowedPrefixes: ['094'],
      courses: [{ courseNumber: '09400101', title: 'Prefix course' }],
    })
    const facultyBucket = bucket({
      requirementGroupId: '009118-1-000:elective-faculty',
      creditsCompleted: 7,
      completedCourses: [
        { courseId: '1', courseNumber: '09400101', creditsEarned: 3.5 },
        { courseId: '2', courseNumber: '00960327', creditsEarned: 3.5 },
      ],
    })
    const allPools = [facultyPool]
    const counted = poolCountedCourseNumbers(facultyPool, facultyBucket, allPools)
    expect(isCountedCourse('00960327', counted)).toBe(true)
    expect(isCountedCourse('09400101', counted)).toBe(true)

    const summary = poolProgressSummary(facultyPool, facultyBucket, undefined, allPools)
    expect(summary.counted).toBe(2)
    expect(summary.creditsCompleted).toBe(7)
  })

  it('matches pool catalog alternatives to bucket course numbers', () => {
    const focusPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      courses: [{ courseNumber: '0960324', title: 'Part 2', alternatives: ['0980413'] }],
    })
    expect(courseMatchesPoolCatalog('0980413', focusPool)).toBe(true)
    expect(courseMatchesPoolCatalog('00960324', focusPool)).toBe(true)
  })

  it('matches canonical catalog numbers to bucket course numbers', () => {
    const focusPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      courses: [{ courseNumber: '0960324', title: 'Part 2' }],
    })
    const facultyBucket = bucket({
      requirementGroupId: '009118-1-000:elective-faculty',
      completedCourses: [{ courseId: '1', courseNumber: '00960324', creditsEarned: 3.5 }],
    })
    const counted = poolCountedCourseNumbers(focusPool, facultyBucket, [focusPool])
    expect(isCountedCourse('0960324', counted)).toBe(true)
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

  it('uses structured chain steps instead of raw course counts', () => {
    const summary = poolProgressSummary(
      pool({
        groupId: '009118-1-000:is-focus-chain-performance',
        rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
        courses: [
          { courseNumber: '00960327', title: 'Part 1' },
          { courseNumber: '00960324', title: 'Part 2' },
          { courseNumber: '00960311', title: 'Part 3 option' },
        ],
      }),
      bucket({
        requirementGroupId: '009118-1-000:elective-faculty',
        eligibilityEnforcement: 'strict_pool',
        completedCourses: [{ courseId: '1', courseNumber: '00960327', creditsEarned: 3.5 }],
      }),
      (key) => key,
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

  it('dedupes cross-track equivalents when one code is counted', () => {
    const courses = preparePoolCourseView(
      [
        { courseNumber: '00960221', title: 'E-commerce models' },
        { courseNumber: '00960211', title: 'E-commerce models', credits: 3.5 },
        { courseNumber: '00960327', title: 'Other' },
      ],
      {
        query: '',
        completedNumbers: new Set(['00960211']),
        filter: 'all',
        sort: 'catalog',
      },
    )
    expect(courses.map((course) => course.courseNumber)).toEqual(['00960211', '00960327'])
  })
})

describe('catalogSearchLink', () => {
  it('builds catalog query links', () => {
    expect(catalogSearchLink('00940345')).toBe('/catalog?q=00940345')
    expect(catalogSearchLink('')).toBe('/catalog')
  })
})

describe('poolCourseFilterCounts', () => {
  it('counts all, counted, and remaining courses with equivalence dedupe', () => {
    const counts = poolCourseFilterCounts(
      [
        { courseNumber: '00940345', title: 'A' },
        { courseNumber: '00940411', title: 'B' },
      ],
      new Set(['00940345']),
    )
    expect(counts).toEqual({ all: 2, counted: 1, remaining: 1 })
  })

  it('collapses cross-track duplicates in filter counts', () => {
    const counts = poolCourseFilterCounts(
      [
        { courseNumber: '00960221', title: 'E-commerce models' },
        { courseNumber: '00960211', title: 'E-commerce models' },
        { courseNumber: '00960327', title: 'Other' },
      ],
      new Set(['00960211']),
    )
    expect(counts).toEqual({ all: 2, counted: 1, remaining: 1 })
  })
})

describe('interpolateTemplate', () => {
  it('replaces placeholders', () => {
    expect(interpolateTemplate('{counted} of {listed}', { counted: 2, listed: 5 })).toBe('2 of 5')
  })
})

describe('isGeneralTechnionPool', () => {
  it('identifies enrichment, free-elective, and physical-education pools', () => {
    expect(isGeneralTechnionPool(pool({ groupId: '009216-1-000:enrichment-pool' }))).toBe(true)
    expect(isGeneralTechnionPool(pool({ groupId: '009216-1-000:free-elective-pool' }))).toBe(true)
    expect(isGeneralTechnionPool(pool({ groupId: '009216-1-000:physical-education-pool' }))).toBe(true)
    expect(isGeneralTechnionPool(pool())).toBe(false)
  })
})

describe('buildTranscriptCourseNumbers', () => {
  it('collects unique course numbers from all buckets', () => {
    const numbers = buildTranscriptCourseNumbers([
      bucket({
        completedCourses: [
          { courseId: '1', courseNumber: '00940345', creditsEarned: 3 },
          { courseId: '2', courseNumber: '00940411', creditsEarned: 3.5 },
        ],
      }),
      bucket({
        requirementGroupId: '009216-1-000:elective-ds',
        completedCourses: [{ courseId: '3', courseNumber: '00940345', creditsEarned: 3 }],
      }),
    ])
    expect([...numbers].sort()).toEqual(['00940345', '00940411'])
  })
})

describe('buildRequiredCurriculumCourseNumbers', () => {
  it('returns only outstanding mandatory and curriculum slots', () => {
    const numbers = buildRequiredCurriculumCourseNumbers(
      [
        bucket({
          isMandatory: true,
          completedCourses: [{ courseId: '1', courseNumber: '00940345', creditsEarned: 4 }],
        }),
        bucket({
          requirementGroupId: '009216-1-000:elective-ds',
          isMandatory: false,
          completedCourses: [{ courseId: '2', courseNumber: '00940411', creditsEarned: 3.5 }],
        }),
      ],
      {
        completedMandatory: [{ courseId: '1', courseNumber: '00940345', creditsEarned: 4 }],
        remainingMandatory: [{ courseNumber: '01040031', courseTitle: 'Intro CS' }],
        curriculumGraph: {
          trackSlug: 'track-dne',
          programCode: '009216-1-000',
          catalogYear: 2025,
          viewDefault: 'semester_swimlanes',
          semesterLanes: [],
          nodes: [{ courseNumber: '00940219', title: 'Data structures', semester: 2 }],
          edges: [],
          bottlenecks: [],
          electiveBuckets: [],
        },
      },
    )
    expect([...numbers].sort()).toEqual(['01040031'])
  })

  it('excludes cross-track equivalents already satisfied on transcript', () => {
    const numbers = buildRequiredCurriculumCourseNumbers([], {
      completedMandatory: [{ courseId: 'done', courseNumber: '00960211' }],
      remainingMandatory: [{ courseNumber: '00960221', courseTitle: 'E-commerce models' }],
      curriculumGraph: {
        trackSlug: 'track-ise',
        programCode: '009118-1-000',
        catalogYear: 2025,
        viewDefault: 'semester_swimlanes',
        semesterLanes: [],
        nodes: [
          {
            nodeId: 'node-ecom',
            courseNumber: '00960221',
            title: 'E-commerce models',
            semester: 4,
            status: 'available',
            credits: { display: '3.5', value: 3.5, uncertain: false },
            alternatives: [],
            dataQuality: {
              manualReviewRequired: false,
              confidence: 'high',
              hasAlternatives: false,
              creditsUncertain: false,
              verifyWithRegistrar: false,
            },
            prerequisiteNumbers: [],
            missingPrerequisites: [],
            isBottleneck: false,
          },
        ],
        edges: [],
        bottlenecks: [],
        electiveBuckets: [],
      },
    })
    expect(numbers.size).toBe(0)
  })

  it('includes curriculum node alternatives in the required set', () => {
    const numbers = buildRequiredCurriculumCourseNumbers([], {
      curriculumGraph: {
        trackSlug: 'track-dne',
        programCode: '009216-1-000',
        catalogYear: 2025,
        viewDefault: 'semester_swimlanes',
        semesterLanes: [],
        nodes: [
          {
            nodeId: 'node-algebra',
            courseNumber: '1040065',
            title: 'Algebra',
            semester: 1,
            status: 'available',
            credits: { display: '5', value: 5, uncertain: false },
            alternatives: ['1040016'],
            dataQuality: {
              manualReviewRequired: false,
              confidence: 'high',
              hasAlternatives: true,
              creditsUncertain: false,
              verifyWithRegistrar: true,
            },
            prerequisiteNumbers: [],
            missingPrerequisites: [],
            isBottleneck: false,
          },
        ],
        edges: [],
        bottlenecks: [],
        electiveBuckets: [],
      },
    })
    expect(isRequiredCurriculumCourse('01040016', numbers)).toBe(true)
    expect(isRequiredCurriculumCourse('1040065', numbers)).toBe(true)
  })
})

describe('localizedPoolTitle', () => {
  it('prefers i18n key over API title', () => {
    const title = localizedPoolTitle(pool({ groupId: '009216-1-000:enrichment-pool' }), (key) =>
      key === 'progress.electiveExplorer.pools.enrichment-pool'
        ? 'University enrichment (CHE)'
        : key,
    )
    expect(title).toBe('University enrichment (CHE)')
  })

  it('falls back to API title when translation is missing', () => {
    expect(localizedPoolTitle(pool({ title: 'Custom pool' }), (key) => key)).toBe('Custom pool')
  })
})

describe('localizedBucketTitle', () => {
  it('uses bucket i18n key when available', () => {
    const title = localizedBucketTitle(
      { requirementGroupId: '009216-1-000:elective-ds', title: 'API title' },
      (key) =>
        key === 'progress.electiveExplorer.buckets.elective-ds' ? 'Data science electives' : key,
    )
    expect(title).toBe('Data science electives')
  })
})

describe('poolCreditsCompleted', () => {
  const facultyBucket = bucket({
    requirementGroupId: '009118-1-000:elective-faculty',
    creditsCompleted: 10.5,
    completedCourses: [
      { courseId: '1', courseNumber: '00960327', creditsEarned: 3.5 },
      { courseId: '2', courseNumber: '09400101', creditsEarned: 3.5 },
      { courseId: '3', courseNumber: '00960324', creditsEarned: 3.5 },
    ],
  })

  it('counts only courses matching the pool catalog list', () => {
    const focusPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      courses: [
        { courseNumber: '00960327', title: 'Part 1' },
        { courseNumber: '00960324', title: 'Part 2' },
      ],
    })
    expect(poolCreditsCompleted(focusPool, facultyBucket, [focusPool])).toBe(7)
  })

  it('counts prefix-matched courses not listed explicitly in the pool catalog', () => {
    const prefixPool = pool({
      groupId: '009118-1-000:is-additional-faculty-electives',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'min_credits', allowedPrefixes: ['094'] },
      courses: [],
      allowedPrefixes: ['094'],
    })
    expect(poolCreditsCompleted(prefixPool, facultyBucket, [prefixPool])).toBe(3.5)
  })

  it('additional faculty pool excludes credits already attributed to focus chains', () => {
    const focusPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      courses: [
        { courseNumber: '00960327', title: 'Part 1' },
        { courseNumber: '00960324', title: 'Part 2' },
      ],
    })
    const prefixPool = pool({
      groupId: '009118-1-000:is-additional-faculty-electives',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'min_credits', allowedPrefixes: ['094', '0096'] },
      courses: [],
      allowedPrefixes: ['094', '0096'],
    })
    const allPools = [focusPool, prefixPool]
    expect(poolCreditsCompleted(focusPool, facultyBucket, allPools)).toBe(7)
    expect(poolCreditsCompleted(prefixPool, facultyBucket, allPools)).toBe(3.5)
  })

  it('uses canonical course numbers when matching pool lists', () => {
    const listPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      courses: [{ courseNumber: '0960324', title: 'Part 2' }],
    })
    expect(courseMatchesPoolCatalog('00960324', listPool)).toBe(true)
    expect(poolCreditsCompleted(listPool, facultyBucket, [listPool])).toBe(3.5)
  })
})

describe('resolvePoolCreditProgress', () => {
  const facultyBucket = bucket({
    requirementGroupId: '009118-1-000:elective-faculty',
    minCredits: 24.5,
    creditsCompleted: 10.5,
    completedCourses: [
      { courseId: '1', courseNumber: '00960327', creditsEarned: 3.5 },
      { courseId: '2', courseNumber: '09400101', creditsEarned: 3.5 },
      { courseId: '3', courseNumber: '00960324', creditsEarned: 3.5 },
    ],
  })

  it('uses full bucket credits for dedicated bucket pools', () => {
    const facultyPool = pool({
      groupId: '009118-1-000:elective-faculty-pool',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      allowedPrefixes: ['094'],
      courses: [],
    })
    const progress = resolvePoolCreditProgress(
      facultyPool,
      facultyBucket,
      'dedicated_bucket_credits',
    )
    expect(progress.displayCreditsCompleted).toBe(10.5)
    expect(progress.bucketCreditsCompleted).toBe(10.5)
  })

  it('uses pool-specific credits for shared sub-pools', () => {
    const prefixPool = pool({
      groupId: '009118-1-000:is-additional-faculty-electives',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'min_credits', allowedPrefixes: ['094'] },
      allowedPrefixes: ['094'],
      courses: [],
    })
    const progress = resolvePoolCreditProgress(prefixPool, facultyBucket, 'shared_bucket_credits', [
      prefixPool,
    ])
    expect(progress.displayCreditsCompleted).toBe(3.5)
    expect(progress.bucketCreditsCompleted).toBe(10.5)
  })
})

describe('poolProgressSummary credits', () => {
  it('reports bucket credits for a sole dedicated pool on its bucket', () => {
    const dsBucket = bucket({
      requirementGroupId: '009216-1-000:elective-ds',
      creditsCompleted: 7,
      completedCourses: [
        { courseId: '1', courseNumber: '00940411', creditsEarned: 3.5 },
        { courseId: '2', courseNumber: '00940345', creditsEarned: 3.5 },
      ],
    })
    const dsPool = pool({
      groupId: '009216-1-000:elective-ds-pool',
      linkedCreditBucketId: '009216-1-000:elective-ds',
    })
    const summary = poolProgressSummary(dsPool, dsBucket, undefined, [dsPool])
    expect(summary.creditsCompleted).toBe(7)
    expect(summary.counted).toBe(2)
  })

  it('reports pool-specific credits when multiple pools share a faculty bucket', () => {
    const facultyBucket = bucket({
      requirementGroupId: '009118-1-000:elective-faculty',
      creditsCompleted: 10.5,
      completedCourses: [
        { courseId: '1', courseNumber: '00960327', creditsEarned: 3.5 },
        { courseId: '2', courseNumber: '09400101', creditsEarned: 3.5 },
        { courseId: '3', courseNumber: '00960324', creditsEarned: 3.5 },
      ],
    })
    const allPools = [
      pool({
        groupId: '009118-1-000:elective-faculty-pool',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        allowedPrefixes: ['094'],
      }),
      pool({
        groupId: '009118-1-000:is-focus-chain-performance',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
        courses: [
          { courseNumber: '00960327', title: 'Part 1' },
          { courseNumber: '00960324', title: 'Part 2' },
        ],
      }),
    ]

    const facultyPoolSummary = poolProgressSummary(allPools[0]!, facultyBucket, undefined, allPools)
    expect(facultyPoolSummary.creditsCompleted).toBe(3.5)
    expect(facultyPoolSummary.counted).toBe(1)

    const sharedSummary = poolProgressSummary(allPools[1]!, facultyBucket, undefined, allPools)
    expect(sharedSummary.creditsCompleted).toBe(7)
    expect(sharedSummary.counted).toBe(2)
    expect(sharedSummary.bucketCreditsCompleted).toBe(10.5)
  })

  it('caps choose_n chain step progress at the required count', () => {
    const summary = poolProgressSummary(
      pool({
        groupId: '009118-1-000:is-behavior-science-chain',
        linkedCreditBucketId: '009118-1-000:elective-faculty',
        rule: { type: 'course_pool', operator: 'choose_n', chooseCount: 1 },
        courses: [
          { courseNumber: '0960600', title: 'Option A' },
          { courseNumber: '0960620', title: 'Option B' },
        ],
      }),
      bucket({
        requirementGroupId: '009118-1-000:elective-faculty',
        completedCourses: [
          { courseId: '1', courseNumber: '0960600', creditsEarned: 3.5 },
          { courseId: '2', courseNumber: '0960620', creditsEarned: 3.5 },
        ],
      }),
      undefined,
      [],
    )
    expect(summary.chainStepsRequired).toBe(1)
    expect(summary.chainStepsCompleted).toBe(1)
  })
})

describe('poolMatchedBucketCourses with assignedPoolGroupId', () => {
  it('uses API pool attribution when present', () => {
    const focusPool = pool({
      groupId: '009118-1-000:is-focus-chain-performance',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_chain', chooseCount: 3 },
      courses: [{ courseNumber: '00960327', title: 'Part 1' }],
    })
    const additionalPool = pool({
      groupId: '009118-1-000:is-additional-faculty-electives',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'min_credits', allowedPrefixes: ['094', '0096'] },
      allowedPrefixes: ['094', '0096'],
      courses: [],
    })
    const facultyBucket = bucket({
      requirementGroupId: '009118-1-000:elective-faculty',
      completedCourses: [
        {
          courseId: '1',
          courseNumber: '00960327',
          creditsEarned: 3.5,
          assignedPoolGroupId: '009118-1-000:is-focus-chain-performance',
        },
        {
          courseId: '2',
          courseNumber: '09400101',
          creditsEarned: 3.5,
          assignedPoolGroupId: '009118-1-000:is-additional-faculty-electives',
        },
      ],
    })
    const allPools = [focusPool, additionalPool]

    expect(poolMatchedBucketCourses(focusPool, facultyBucket, allPools)).toHaveLength(1)
    expect(poolMatchedBucketCourses(additionalPool, facultyBucket, allPools)).toHaveLength(1)
    expect(poolCreditsCompleted(additionalPool, facultyBucket, allPools)).toBe(3.5)
  })
})

describe('choose_n pool matching', () => {
  it('counts at most chooseCount courses toward the pool', () => {
    const behaviorPool = pool({
      groupId: '009118-1-000:is-behavior-science-chain',
      linkedCreditBucketId: '009118-1-000:elective-faculty',
      rule: { type: 'course_pool', operator: 'choose_n', chooseCount: 1 },
      courses: [
        { courseNumber: '0960600', title: 'Option A' },
        { courseNumber: '0960620', title: 'Option B' },
      ],
    })
    const facultyBucket = bucket({
      requirementGroupId: '009118-1-000:elective-faculty',
      completedCourses: [
        { courseId: '1', courseNumber: '0960600', creditsEarned: 3.5 },
        { courseId: '2', courseNumber: '0960620', creditsEarned: 3.5 },
      ],
    })
    expect(poolMatchedBucketCourses(behaviorPool, facultyBucket, [behaviorPool])).toHaveLength(1)
    expect(poolCreditsCompleted(behaviorPool, facultyBucket, [behaviorPool])).toBe(3.5)
  })
})

describe('ruleBadgeTone', () => {
  it('maps pool operators to badge tones', () => {
    expect(ruleBadgeTone('choose_chain')).toBe('primary')
    expect(ruleBadgeTone('choose_n')).toBe('warning')
    expect(ruleBadgeTone('choose_credits')).toBe('success')
    expect(ruleBadgeTone('min_credits')).toBe('neutral')
  })
})
