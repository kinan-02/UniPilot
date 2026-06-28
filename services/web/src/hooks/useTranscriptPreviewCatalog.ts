import { useQuery } from '@tanstack/react-query'
import { fetchCatalogSummariesByNumbers } from '../lib/transcriptImportDisplay'
import type { TranscriptParsePreview } from '../types/api'

export const TRANSCRIPT_PREVIEW_CATALOG_KEY = ['transcript-preview-catalog'] as const

export function useTranscriptPreviewCatalog(preview: TranscriptParsePreview | null) {
  const courseNumbers = preview?.courses.map((course) => course.courseNumber) ?? []

  return useQuery({
    queryKey: [...TRANSCRIPT_PREVIEW_CATALOG_KEY, courseNumbers],
    queryFn: () => fetchCatalogSummariesByNumbers(courseNumbers),
    enabled: courseNumbers.length > 0,
    staleTime: 5 * 60 * 1000,
  })
}
