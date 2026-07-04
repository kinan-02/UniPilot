import type { SimulationOperation, SimulationResult } from '../types/api'

export function mapSimulationResult(raw: unknown): SimulationResult | null {
  if (!raw || typeof raw !== 'object') {
    return null
  }

  const document = raw as Record<string, unknown>
  const id =
    typeof document.id === 'string'
      ? document.id
      : typeof document._id === 'string'
        ? document._id
        : null
  const scenarioId =
    typeof document.scenarioId === 'string'
      ? document.scenarioId
      : typeof document.scenarioId === 'object' && document.scenarioId !== null
        ? String((document.scenarioId as { toString?: () => string }).toString?.() ?? '')
        : null

  if (!id || !scenarioId) {
    return null
  }

  return {
    id,
    scenarioId,
    status: typeof document.status === 'string' ? document.status : null,
    beforeSnapshot:
      document.beforeSnapshot && typeof document.beforeSnapshot === 'object'
        ? (document.beforeSnapshot as SimulationResult['beforeSnapshot'])
        : {},
    afterSnapshot:
      document.afterSnapshot && typeof document.afterSnapshot === 'object'
        ? (document.afterSnapshot as SimulationResult['afterSnapshot'])
        : {},
    deltas:
      document.deltas && typeof document.deltas === 'object'
        ? (document.deltas as SimulationResult['deltas'])
        : {},
    summary: typeof document.summary === 'string' ? document.summary : null,
    narrative: typeof document.narrative === 'string' ? document.narrative : null,
    warnings: Array.isArray(document.warnings)
      ? document.warnings.filter((item): item is string => typeof item === 'string')
      : [],
    jobId: typeof document.jobId === 'string' ? document.jobId : null,
    generatedAt: typeof document.generatedAt === 'string' ? document.generatedAt : null,
    createdAt: typeof document.createdAt === 'string' ? document.createdAt : null,
  }
}

export function simulationResultFromJobResult(
  result: Record<string, unknown> | null | undefined,
): SimulationResult | null {
  if (!result) {
    return null
  }
  const nested = result.simulationResult
  return mapSimulationResult(nested)
}

export function formatOperationLabel(operation: SimulationOperation): string {
  switch (operation.type) {
    case 'drop_course':
      return `Drop ${operation.courseNumber}`
    case 'add_course':
      return `Add ${operation.courseNumber}${operation.semesterCode ? ` (${operation.semesterCode})` : ''}`
    case 'add_planned_course':
      return `Plan ${operation.courseNumber}`
    case 'change_track':
      return `Track → ${operation.trackSlug}`
    default:
      return 'Unknown operation'
  }
}

export function formatCreditDelta(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) {
    return '—'
  }
  if (value > 0) {
    return `+${value}`
  }
  return String(value)
}
