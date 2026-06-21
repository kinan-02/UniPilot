import { describe, expect, it } from 'vitest'
import { buildPlanChanges } from './plannerChanges'
import type { PlannerInsights } from '../types/api'

describe('buildPlanChanges', () => {
  it('returns empty list when insights are missing', () => {
    expect(buildPlanChanges()).toEqual([])
  })

  it('collects stale, lesson, prerequisite, and exam warnings', () => {
    const insights: PlannerInsights = {
      staleCourseWarnings: [{ courseNumber: '02340114', message: 'Offering removed' }],
      lessonSelectionWarnings: [
        { courseNumber: '02340114', type: 'missing_selection', message: 'Choose lessons' },
      ],
      courseWarnings: [
        { courseNumber: '104031', courseId: '104031', status: 'missing', message: 'Missing prereq' },
        { courseNumber: '234114', courseId: '234114', status: 'satisfied', message: 'OK' },
      ],
      examSummary: {
        exams: [],
        warnings: [{ type: 'same_day', message: 'Two exams same day', courseNumbers: ['104031', '234114'] }],
      },
    }

    const changes = buildPlanChanges(insights)
    expect(changes).toHaveLength(4)
    expect(changes.map((item) => item.type)).toEqual(
      expect.arrayContaining(['stale_offering', 'missing_selection', 'missing', 'same_day']),
    )
  })
})
