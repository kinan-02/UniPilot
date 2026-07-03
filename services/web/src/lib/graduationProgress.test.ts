import { describe, expect, it } from 'vitest'
import {
  apiRemainingMandatoryCourses,
  bucketCompletionPercent,
  hasActionableGaps,
  hasDegreeCreditBucketGap,
  isGeneralTechnionBucket,
  overlapIneligibleCredits,
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
    expect(mandatory).toHaveLength(1)
    expect(mandatory[0]?.requirementGroupId).toBe('009216-1-000:core-mandatory')
    expect(elective).toHaveLength(1)
    expect(elective[0]?.requirementGroupId).toBe('009216-1-000:elective-ds')
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
        ineligibleCredits: [{ courseNumber: '03940580', reason: 'not_assigned_to_requirement' }],
      }),
    ).toBe(true)
    expect(
      hasActionableGaps({
        ...base,
        ineligibleCredits: [
          { courseNumber: '02340117', reason: 'overlap_no_additional_credit', creditsEarned: 4 },
        ],
      }),
    ).toBe(false)
  })

  it('returns API remaining mandatory courses without client re-filtering', () => {
    const progress: GraduationProgress = {
      degreeId: 'abc',
      completedCredits: 70,
      totalRequiredCredits: 155,
      creditsRemaining: 85,
      completionPercentage: 45,
      statusSummary: 'in_progress',
      remainingMandatoryCourses: [
        { courseId: 'm1', courseNumber: '02340123', courseTitle: 'OS' },
        { courseId: 'm2', courseNumber: '02360343', courseTitle: 'Theory' },
      ],
    }
    expect(apiRemainingMandatoryCourses(progress).map((course) => course.courseNumber)).toEqual([
      '02340123',
      '02360343',
    ])
  })

  it('counts overlap ineligible credits in attention totals', () => {
    const progress: GraduationProgress = {
      degreeId: 'abc',
      completedCredits: 70,
      totalRequiredCredits: 155,
      creditsRemaining: 85,
      completionPercentage: 45,
      statusSummary: 'in_progress',
      ineligibleCredits: [
        { courseId: 'o1', courseNumber: '02340117', creditsEarned: 4, reason: 'overlap_no_additional_credit' },
      ],
    }
    expect(overlapIneligibleCredits(progress)).toHaveLength(1)
  })

  it('detects credit/bucket gaps when open buckets and ineligible credits coexist', () => {
    const gap = hasDegreeCreditBucketGap({
      degreeId: 'd1',
      completedCredits: 95,
      transcriptCreditsTotal: 95,
      degreeAppliedCredits: 80,
      totalRequiredCredits: 155,
      creditsRemaining: 60,
      completionPercentage: 61.3,
      statusSummary: 'in_progress',
      missingRequirements: [{ requirementId: 'r1' } as never],
      ineligibleCredits: [{ courseId: 'x', creditsEarned: 15, reason: 'not_assigned_to_requirement' }],
    })
    expect(gap).toBe(true)
  })

  it('detects gap when credit buckets look complete but mandatory matrix courses remain', () => {
    const gap = hasDegreeCreditBucketGap({
      degreeId: 'd1',
      completedCredits: 155,
      totalRequiredCredits: 155,
      creditsRemaining: 0,
      completionPercentage: 100,
      statusSummary: 'complete',
      missingRequirements: [],
      remainingMandatoryCourses: [{ courseNumber: '00940345', courseTitle: 'Discrete math' }],
    })
    expect(gap).toBe(true)
  })

  it('does not flag low-completion students with remaining mandatory courses only', () => {
    const gap = hasDegreeCreditBucketGap({
      degreeId: 'd1',
      completedCredits: 7.5,
      totalRequiredCredits: 155,
      creditsRemaining: 147.5,
      completionPercentage: 4.8,
      statusSummary: 'in_progress',
      missingRequirements: [],
      remainingMandatoryCourses: [{ courseNumber: '00940345', courseTitle: 'Discrete math' }],
    })
    expect(gap).toBe(false)
  })
})
