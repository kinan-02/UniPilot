import { describe, expect, it } from 'vitest'
import {
  bucketCompletionPercent,
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

  it('partitions mandatory and elective buckets', () => {
    const buckets = [
      sampleBucket({ requirementGroupId: 'a', isMandatory: true }),
      sampleBucket({ requirementGroupId: 'b', isMandatory: false }),
    ]
    const { mandatory, elective } = partitionRequirementBuckets(buckets)
    expect(mandatory).toHaveLength(1)
    expect(elective).toHaveLength(1)
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
})
