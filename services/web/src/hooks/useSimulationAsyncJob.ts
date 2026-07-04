import { useQuery } from '@tanstack/react-query'
import { advisorApi } from '../api/endpoints'
import type { AiJob, SimulationResult } from '../types/api'
import { simulationResultFromJobResult } from '../lib/simulationMappers'

const TERMINAL_STATUSES = new Set(['completed', 'failed'])

export function useSimulationAsyncJob(jobId: string | null) {
  const query = useQuery({
    queryKey: ['simulation-job', jobId],
    queryFn: async () => {
      if (!jobId) {
        return null
      }
      const data = await advisorApi.getJob(jobId)
      return data.job
    },
    enabled: Boolean(jobId),
    refetchInterval: (currentQuery) => {
      const status = currentQuery.state.data?.status
      if (!status || TERMINAL_STATUSES.has(status)) {
        return false
      }
      return 2000
    },
  })

  const job: AiJob | null = query.data ?? null
  const isPolling = Boolean(jobId && job && !TERMINAL_STATUSES.has(job.status))
  const simulationResult: SimulationResult | null =
    job?.status === 'completed' ? simulationResultFromJobResult(job.result ?? null) : null

  return {
    job,
    isPolling,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    simulationResult,
  }
}
