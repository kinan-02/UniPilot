import type { QueryClient } from '@tanstack/react-query'
import { useQuery } from '@tanstack/react-query'
import { recommendationsApi } from '../api/endpoints'
import type { AiRecommendation } from '../types/api'

export const RECOMMENDATIONS_QUERY_KEY = ['recommendations', 'active'] as const

export type RecommendationsListResult = {
  recommendations: AiRecommendation[]
  pagination: { total: number; page: number; limit: number }
}

const WATCHDOG_REFETCH_DELAYS_MS = [1000, 4000, 10000] as const

export function useRecommendationsQuery(enabled: boolean) {
  return useQuery({
    queryKey: RECOMMENDATIONS_QUERY_KEY,
    queryFn: () => recommendationsApi.list(),
    enabled,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  })
}

export async function invalidateRecommendations(queryClient: QueryClient): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: RECOMMENDATIONS_QUERY_KEY })
  for (const delayMs of WATCHDOG_REFETCH_DELAYS_MS) {
    window.setTimeout(() => {
      void queryClient.refetchQueries({ queryKey: RECOMMENDATIONS_QUERY_KEY })
    }, delayMs)
  }
}
