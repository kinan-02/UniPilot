import { describe, expect, it } from 'vitest'
import {
  formatCreditDelta,
  formatOperationLabel,
  mapSimulationResult,
  simulationResultFromJobResult,
} from './simulationMappers'

describe('simulationMappers', () => {
  it('maps public simulation result documents', () => {
    const mapped = mapSimulationResult({
      id: 'result-1',
      scenarioId: 'scenario-1',
      summary: 'Credits decreased',
      beforeSnapshot: { graduation: { completedCredits: 10 } },
      afterSnapshot: { graduation: { completedCredits: 7 } },
      deltas: { progress: { completedCreditsDelta: -3 } },
      warnings: ['Check prerequisites'],
    })

    expect(mapped?.id).toBe('result-1')
    expect(mapped?.scenarioId).toBe('scenario-1')
    expect(mapped?.warnings).toEqual(['Check prerequisites'])
  })

  it('extracts simulation result from async job payload', () => {
    const mapped = simulationResultFromJobResult({
      simulationResult: {
        _id: 'mongo-id',
        scenarioId: 'scenario-1',
        summary: 'Done',
        beforeSnapshot: {},
        afterSnapshot: {},
        deltas: {},
      },
    })

    expect(mapped?.id).toBe('mongo-id')
    expect(mapped?.summary).toBe('Done')
  })

  it('formats operation labels', () => {
    expect(formatOperationLabel({ type: 'drop_course', courseNumber: '00940219' })).toBe(
      'Drop 00940219',
    )
    expect(formatCreditDelta(2)).toBe('+2')
    expect(formatCreditDelta(-1)).toBe('-1')
  })
})
