import { describe, expect, it } from 'vitest'
import {
  buildAddPlannedCourseText,
  buildDropCourseText,
  buildPlanWhatIfText,
  buildRiskMitigationText,
  buildSimulationPath,
  detectSimulationIntent,
  extractCourseNumbers,
} from './simulationLinks'
import type { SemesterPlan } from '../types/api'

describe('simulationLinks', () => {
  it('detects what-if phrasing', () => {
    expect(detectSimulationIntent('What if I drop course 00940219?')).toBe(true)
    expect(detectSimulationIntent('מה אם אוריד קורס 00940219')).toBe(true)
    expect(detectSimulationIntent('Tell me about prerequisites')).toBe(false)
  })

  it('builds simulation paths with auto-build', () => {
    expect(buildSimulationPath({ text: 'What if I drop 00940219?' })).toBe(
      '/simulations?text=What+if+I+drop+00940219%3F&autoBuild=1',
    )
    expect(
      buildSimulationPath({
        text: 'Plan change',
        planId: 'abc123',
        autoBuild: false,
      }),
    ).toBe('/simulations?text=Plan+change&planId=abc123')
  })

  it('extracts course numbers and builds helper texts', () => {
    expect(extractCourseNumbers('Risk in 00940219 and 02360444')).toEqual(['00940219', '02360444'])
    expect(buildDropCourseText('00940219')).toContain('00940219')
    expect(buildAddPlannedCourseText('02360444')).toContain('02360444')
  })

  it('builds plan and risk mitigation prompts', () => {
    const plan: SemesterPlan = {
      id: 'plan-1',
      status: 'active',
      version: 1,
      plannerType: 'manual',
      semesters: [
        {
          semesterCode: '2025-2',
          plannedCourses: [
            { courseId: 'c1', courseNumber: '00940219', credits: 3 },
            { courseId: 'c2', courseNumber: '02360444', credits: 3 },
          ],
        },
      ],
    }

    expect(buildPlanWhatIfText(plan)).toContain('00940219')
    expect(buildPlanWhatIfText(plan)).toContain('02360444')

    expect(
      buildRiskMitigationText(
        {
          title: 'Heavy workload',
          message: 'Consider adding 00940219 next term',
        },
        'plan-1',
      ),
    ).toContain('00940219')
  })
})
