import { describe, expect, it } from 'vitest'
import {
  applyScheduleSelections,
  formatAutoPickStatus,
  mergeSuggestedCourses,
} from './plannerAutoAssist'
import type { PlannedCourse } from '../types/api'
import type { DraftCourse } from '../types/planner'

describe('plannerAutoAssist', () => {
  const baseLabels = {
    success: 'Added {count}',
    successPartial: 'Partial {count}',
    successPartialMerge: 'Added {added}, filtered {filtered}',
    empty: 'Empty',
    emptyWorkload: 'Workload {max}',
    emptyConflicts: 'Conflicts',
    emptyUnavailable: 'Unavailable',
    emptyMixed: 'Mixed: {reasons}',
    emptyReasonWorkload: 'limit {max}',
    emptyReasonConflicts: 'clashes',
    emptyReasonUnavailable: 'no schedule',
    noNewCourses: 'No new',
    mergeFiltered: 'Filtered {count}',
    overBudget: 'Over {credits}/{max}',
  }
  it('merges suggested courses without duplicates', () => {
    const current: DraftCourse[] = [
      {
        courseId: 'a',
        courseNumber: '10401',
        courseTitle: 'Physics 1',
        credits: 5,
        isActive: true,
      },
    ]
    const suggested: PlannedCourse[] = [
      {
        courseId: 'a',
        courseNumber: '10401',
        courseTitle: 'Physics 1',
        credits: 5,
      },
      {
        courseId: 'b',
        courseNumber: '10403',
        courseTitle: 'Physics 2',
        credits: 5,
        selectedLessonEvents: [{ eventId: 'lec-1', type: 'lecture' }],
      },
    ]

    const merged = mergeSuggestedCourses(current, suggested)
    expect(merged).toHaveLength(2)
    expect(merged[1]?.courseNumber).toBe('10403')
    expect(merged[1]?.selectedLessonEvents).toEqual([{ eventId: 'lec-1', type: 'lecture' }])
  })

  it('applies schedule selections by course number', () => {
    const courses: DraftCourse[] = [
      {
        courseId: 'a',
        courseNumber: '10401',
        courseTitle: 'Physics 1',
        credits: 5,
        isActive: true,
      },
      {
        courseId: 'b',
        courseNumber: '10403',
        courseTitle: 'Physics 2',
        credits: 5,
        isActive: true,
      },
    ]

    const next = applyScheduleSelections(courses, [
      {
        courseNumber: '10403',
        selectedLessonEvents: [{ eventId: 'tut-2', type: 'tutorial' }],
      },
    ])

    expect(next[0]?.selectedLessonEvents).toBeUndefined()
    expect(next[1]?.selectedLessonEvents).toEqual([{ eventId: 'tut-2', type: 'tutorial' }])
  })

  it('ignores duplicate entries in the suggestion payload', () => {
    const suggested: PlannedCourse[] = [
      {
        courseId: 'b',
        courseNumber: '10403',
        courseTitle: 'Physics 2',
        credits: 5,
      },
      {
        courseId: 'b',
        courseNumber: '10403',
        courseTitle: 'Physics 2',
        credits: 5,
      },
    ]

    const merged = mergeSuggestedCourses([], suggested)
    expect(merged).toHaveLength(1)
  })

  it('formats localized partial success when credits are below max', () => {
    const message = formatAutoPickStatus(
      2,
      {
        selectedCount: 2,
        totalRecommendedCredits: 4,
        semesterTotalCredits: 10,
        maxCredits: 18,
        partialPlan: true,
      },
      {
        ...baseLabels,
        success: 'Added {count} ({credits} cr)',
        successPartial: 'Added {count} ({credits}/{max} cr), no more available',
      },
      (value) => String(value),
    )

    expect(message).toBe('Added 2 (10/18 cr), no more available')
  })

  it('formats no-new-courses when suggestions were already applied', () => {
    const message = formatAutoPickStatus(
      0,
      {
        selectedCount: 0,
        totalRecommendedCredits: 0,
        semesterTotalCredits: 7.5,
        reservedCredits: 7.5,
        maxCredits: 18,
        partialPlan: true,
      },
      { ...baseLabels, noNewCourses: 'Already in list' },
      String,
    )

    expect(message).toBe('Already in list')
  })

  it('formats over-budget when the draft already exceeds max credits', () => {
    const message = formatAutoPickStatus(
      0,
      {
        selectedCount: 0,
        totalRecommendedCredits: 0,
        semesterTotalCredits: 12,
        reservedCredits: 12,
        maxCredits: 10,
      },
      baseLabels,
      String,
    )

    expect(message).toBe('Over 12/10')
  })

  it('formats full success when credits reach max', () => {
    const message = formatAutoPickStatus(
      3,
      { selectedCount: 3, totalRecommendedCredits: 18, maxCredits: 18, partialPlan: false },
      {
        ...baseLabels,
        success: 'Added {count} ({credits}/{max})',
      },
      String,
    )

    expect(message).toBe('Added 3 (18/18)')
  })

  it('formats empty state when nothing was suggested', () => {
    const message = formatAutoPickStatus(
      0,
      { selectedCount: 0, totalRecommendedCredits: 0, maxCredits: 18, emptyPlan: true },
      { ...baseLabels, empty: 'Nothing matched' },
      String,
    )

    expect(message).toBe('Nothing matched')
  })

  it('skips courses already on the maybe list', () => {
    const merged = mergeSuggestedCourses(
      [],
      [
        {
          courseId: 'b',
          courseNumber: '10403',
          courseTitle: 'Physics 2',
          credits: 5,
        },
      ],
      { excludedCourseNumbers: ['10403'] },
    )

    expect(merged).toHaveLength(0)
  })

  it('merges by course number when courseId differs', () => {
    const current: DraftCourse[] = [
      {
        courseId: 'old-id',
        courseNumber: '10401',
        courseTitle: 'Physics 1',
        credits: 5,
        isActive: true,
      },
    ]
    const suggested: PlannedCourse[] = [
      {
        courseId: 'new-id',
        courseNumber: '10401',
        courseTitle: 'Physics 1',
        credits: 5,
      },
    ]

    const merged = mergeSuggestedCourses(current, suggested)
    expect(merged).toHaveLength(1)
  })

  it('treats padded and canonical course numbers as duplicates', () => {
    const current: DraftCourse[] = [
      {
        courseId: 'a',
        courseNumber: '0940345',
        courseTitle: 'Discrete math',
        credits: 4,
        isActive: true,
      },
    ]
    const suggested: PlannedCourse[] = [
      {
        courseId: 'b',
        courseNumber: '00940345',
        courseTitle: 'Discrete math',
        credits: 4,
      },
      {
        courseId: 'c',
        courseNumber: '01040031',
        courseTitle: 'Intro CS',
        credits: 3.5,
      },
    ]

    const merged = mergeSuggestedCourses(current, suggested)
    expect(merged).toHaveLength(2)
    expect(merged[1]?.courseNumber).toBe('01040031')
  })

  it('skips maybe-list courses when numbers use different padding', () => {
    const merged = mergeSuggestedCourses(
      [],
      [
        {
          courseId: 'b',
          courseNumber: '00940345',
          courseTitle: 'Discrete math',
          credits: 4,
        },
      ],
      { excludedCourseNumbers: ['0940345'] },
    )

    expect(merged).toHaveLength(0)
  })

  it('formats merge-filtered when suggestions were blocked on the client', () => {
    const message = formatAutoPickStatus(
      0,
      {
        selectedCount: 2,
        totalRecommendedCredits: 7,
        semesterTotalCredits: 7,
        reservedCredits: 0,
        maxCredits: 18,
      },
      { ...baseLabels, mergeFiltered: 'Filtered {count}' },
      String,
    )

    expect(message).toBe('Filtered 2')
  })

  it('formats partial merge when some suggestions were filtered on the client', () => {
    const message = formatAutoPickStatus(
      2,
      {
        selectedCount: 4,
        totalRecommendedCredits: 8,
        semesterTotalCredits: 12,
        maxCredits: 18,
      },
      { ...baseLabels, successPartialMerge: 'Added {added}, skipped {filtered}' },
      String,
    )

    expect(message).toBe('Added 2, skipped 2')
  })

  it('formats workload-limited empty state', () => {
    const message = formatAutoPickStatus(
      0,
      {
        selectedCount: 0,
        skippedDueToWorkload: [{ courseNumber: '10401' }],
        maxCredits: 5,
      },
      { ...baseLabels, emptyWorkload: 'Cap {max}' },
      String,
    )

    expect(message).toBe('Cap 5')
  })

  it('formats conflict-limited empty state', () => {
    const message = formatAutoPickStatus(
      0,
      {
        selectedCount: 0,
        skippedDueToConflicts: [{ courseNumber: '10401' }],
      },
      { ...baseLabels, emptyConflicts: 'Schedule clash' },
      String,
    )

    expect(message).toBe('Schedule clash')
  })

  it('formats mixed empty state when multiple skip reasons apply', () => {
    const message = formatAutoPickStatus(
      0,
      {
        selectedCount: 0,
        skippedDueToWorkload: [{ courseNumber: '10401' }],
        skippedDueToConflicts: [{ courseNumber: '10403' }],
        maxCredits: 5,
      },
      baseLabels,
      String,
    )

    expect(message).toBe('Mixed: limit 5, clashes')
  })
})
