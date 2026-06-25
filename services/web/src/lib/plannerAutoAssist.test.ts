import { describe, expect, it } from 'vitest'
import {
  applyScheduleSelections,
  formatAutoPickStatus,
  mergeSuggestedCourses,
} from './plannerAutoAssist'
import type { PlannedCourse } from '../types/api'
import type { DraftCourse } from '../types/planner'

describe('plannerAutoAssist', () => {
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
        success: 'Added {count} ({credits} cr)',
        successPartial: 'Added {count} ({credits}/{max} cr), no more available',
        empty: 'Empty',
        noNewCourses: 'No new',
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
      {
        success: 'Added {count}',
        successPartial: 'Partial {count}',
        empty: 'Empty',
        noNewCourses: 'Already in list',
      },
      String,
    )

    expect(message).toBe('Already in list')
  })

  it('formats full success when credits reach max', () => {
    const message = formatAutoPickStatus(
      3,
      { selectedCount: 3, totalRecommendedCredits: 18, maxCredits: 18, partialPlan: false },
      {
        success: 'Added {count} ({credits}/{max})',
        successPartial: 'Partial {count}',
        empty: 'Empty',
        noNewCourses: 'No new',
      },
      String,
    )

    expect(message).toBe('Added 3 (18/18)')
  })

  it('formats empty state when nothing was suggested', () => {
    const message = formatAutoPickStatus(
      0,
      { selectedCount: 0, totalRecommendedCredits: 0, maxCredits: 18, emptyPlan: true },
      {
        success: 'Added {count}',
        successPartial: 'Partial',
        empty: 'Nothing matched',
        noNewCourses: 'No new',
      },
      String,
    )

    expect(message).toBe('Nothing matched')
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
})
