import { useQuery } from '@tanstack/react-query'
import { transcriptApi } from '../api/endpoints'

export const TRANSCRIPT_QUERY_KEY = ['transcript'] as const

export function useTranscriptRecords() {
  return useQuery({
    queryKey: TRANSCRIPT_QUERY_KEY,
    queryFn: () => transcriptApi.listAll(),
  })
}
