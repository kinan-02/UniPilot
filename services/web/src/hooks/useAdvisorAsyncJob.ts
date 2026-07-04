import { useQuery } from '@tanstack/react-query'
import { advisorApi } from '../api/endpoints'
import type { AdvisorReply, AiJob } from '../types/api'

const TERMINAL_STATUSES = new Set(['completed', 'failed'])

function advisorReplyFromJob(job: AiJob): AdvisorReply | null {
  const advisor = job.result?.advisor
  if (!advisor || typeof advisor !== 'object') {
    return null
  }

  const payload = advisor as Record<string, unknown>
  const answer = typeof payload.answer === 'string' ? payload.answer : ''
  if (!answer) {
    return null
  }

  return {
    question: typeof payload.question === 'string' ? payload.question : '',
    answer,
    confidence: typeof payload.confidence === 'string' ? payload.confidence : 'medium',
    courseIds: Array.isArray(payload.courseIds) ? (payload.courseIds as string[]) : [],
    wikiSlugs: Array.isArray(payload.wikiSlugs) ? (payload.wikiSlugs as string[]) : [],
    sources: Array.isArray(payload.sources) ? (payload.sources as string[]) : [],
    contacts: Array.isArray(payload.contacts) ? (payload.contacts as string[]) : [],
    eligibility:
      payload.eligibility && typeof payload.eligibility === 'object'
        ? (payload.eligibility as Record<string, unknown>)
        : null,
    semesterResolution:
      payload.semesterResolution && typeof payload.semesterResolution === 'object'
        ? (payload.semesterResolution as Record<string, unknown>)
        : null,
    retrievalStatus: typeof payload.retrievalStatus === 'string' ? payload.retrievalStatus : null,
    agentTrace:
      payload.agentTrace && typeof payload.agentTrace === 'object'
        ? (payload.agentTrace as AdvisorReply['agentTrace'])
        : undefined,
  }
}

export function useAdvisorAsyncJob(jobId: string | null) {
  const query = useQuery({
    queryKey: ['advisor-job', jobId],
    queryFn: async () => {
      if (!jobId) return null
      const data = await advisorApi.getJob(jobId)
      return data.job
    },
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (!status || TERMINAL_STATUSES.has(status)) {
        return false
      }
      return 2000
    },
  })

  const job = query.data ?? null
  const isPolling = Boolean(jobId && job && !TERMINAL_STATUSES.has(job.status))
  const advisorReply = job?.status === 'completed' ? advisorReplyFromJob(job) : null

  return {
    job,
    isPolling,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    advisorReply,
    conversation:
      job?.status === 'completed' && job.result?.conversation
        ? (job.result.conversation as Record<string, unknown>)
        : null,
  }
}
