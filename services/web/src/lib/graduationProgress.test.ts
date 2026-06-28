import { describe, expect, it } from 'vitest'
import {
  bucketCompletionPercent,
  filterRemainingMandatoryCourses,
  hasActionableGaps,
  isGeneralTechnionBucket,
  partitionRequirementBuckets,
  progressCatalogSubtitle,
  statusBadgeTone,
} from './graduationProgress'
import type { GraduationProgress, RequirementProgressEntry } from '../types/api'

const sampleBucket = (overrides: Partial<RequirementProgressEntry> = {}): RequirementProgressEntry => ({
  requirementGroupId: 'prog:core',
  title: 'Core',
  status: 'in_progress',
  minCredits: 10,
  creditsCompleted: 4,
  creditsRemaining: 6,
  isMandatory: true,
  ...overrides,
})

describe('graduationProgress helpers', () => {
  it('computes bucket completion percent', () => {
    expect(bucketCompletionPercent(4, 10)).toBe(40)
    expect(bucketCompletionPercent(12, 10)).toBe(100)
    expect(bucketCompletionPercent(0, 0)).toBe(0)
  })

  it('maps status to badge tones', () => {
    expect(statusBadgeTone('complete')).toBe('success')
    expect(statusBadgeTone('in_progress')).toBe('primary')
    expect(statusBadgeTone('not_started')).toBe('neutral')
  })

  it('partitions mandatory, elective, and general technion buckets', () => {
    const buckets = [
      sampleBucket({ requirementGroupId: '009216-1-000:core-mandatory', isMandatory: true }),
      sampleBucket({ requirementGroupId: '009216-1-000:elective-ds', isMandatory: true }),
      sampleBucket({ requirementGroupId: '009216-1-000:enrichment', isMandatory: false }),
      sampleBucket({ requirementGroupId: '009216-1-000:free-elective', isMandatory: false }),
    ]
    const { mandatory, elective, generalTechnion } = partitionRequirementBuckets(buckets)
    expect(mandatory).toHaveLength(2)
    expect(elective).toHaveLength(0)
    expect(generalTechnion).toHaveLength(2)
  })

  it('builds catalog subtitle from degree metadata', () => {
    const progress: GraduationProgress = {
      degreeId: 'abc',
      degreeName: 'Industrial Engineering',
      catalogYear: 2025,
      catalogVersion: '2025.1',
      completedCredits: 0,
      totalRequiredCredits: 155,
      creditsRemaining: 155,
      completionPercentage: 0,
      statusSummary: 'not_started',
    }
    expect(progressCatalogSubtitle(progress)).toBe('Industrial Engineering · 2025 · v2025.1')
  })

  it('identifies general Technion buckets by suffix', () => {
    expect(isGeneralTechnionBucket({ requirementGroupId: '009216-1-000:enrichment' })).toBe(true)
    expect(isGeneralTechnionBucket({ requirementGroupId: '009216-1-000:core-math' })).toBe(false)
  })

  it('detects actionable gaps from remaining mandatory, missing, or ineligible credits', () => {
    const base: GraduationProgress = {
      degreeId: 'abc',
      completedCredits: 0,
      totalRequiredCredits: 155,
      creditsRemaining: 155,
      completionPercentage: 0,
      statusSummary: 'not_started',
    }
    expect(hasActionableGaps(base)).toBe(false)
    expect(
      hasActionableGaps({
        ...base,
        remainingMandatoryCourses: [{ courseNumber: '00940345', courseTitle: 'Math' }],
      }),
    ).toBe(true)
    expect(
      hasActionableGaps({
        ...base,
        ineligibleCredits: [{ courseNumber: '03940580', reason: 'wrong bucket' }],
      }),
    ).toBe(true)
  })

  it('filters remaining mandatory courses already satisfied by parallel completion', () => {
    const graph = {
      trackSlug: 'track',
      programCode: '009216-1-000',
      catalogYear: 2025,
      viewDefault: 'semester_swimlanes' as const,
      semesterLanes: [],
      nodes: [
        {
          nodeId: 'node-algebra',
          courseNumber: '1040065',
          title: 'Algebra',
          semester: 1,
          status: 'available' as const,
          credits: { display: '5', value: 5, uncertain: false },
          alternatives: ['1040016'],
          dataQuality: {
            manualReviewRequired: false,
            confidence: 'high' as const,
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
    }
    const remaining = filterRemainingMandatoryCourses(
      [
        { courseId: 'matrix:1040065', courseNumber: '1040065' },
        { courseId: 'matrix:01040031', courseNumber: '01040031' },
      ],
      [{ courseId: 'real-id', courseNumber: '1040016' }],
      graph,
    )
    expect(remaining.map((course) => course.courseNumber)).toEqual(['01040031'])
  })
})
