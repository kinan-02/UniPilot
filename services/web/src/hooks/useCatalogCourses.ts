import { useCallback, useMemo } from 'react'
import { useInfiniteQuery } from '@tanstack/react-query'
import { catalogApi } from '../api/endpoints'

export const CATALOG_PAGE_SIZE = 30

export type CatalogFilters = {
  query: string
  faculty: string
  minCredits?: number
  maxCredits?: number
}

function buildCourseSearchParams(filters: CatalogFilters, offset: number) {
  const params: Record<string, string | number | boolean> = {
    limit: CATALOG_PAGE_SIZE,
    offset,
  }
  const trimmed = filters.query.trim()
  if (trimmed) {
    params.q = trimmed
    if (/^0\d{7}$/.test(trimmed)) {
      params.courseNumber = trimmed
    }
  }
  if (filters.faculty) params.faculty = filters.faculty
  if (filters.minCredits != null) params.minCredits = filters.minCredits
  if (filters.maxCredits != null) params.maxCredits = filters.maxCredits
  return params
}

export function useCatalogCourses(filters: CatalogFilters) {
  const query = useInfiniteQuery({
    queryKey: [
      'catalog-courses',
      filters.query.trim(),
      filters.faculty,
      filters.minCredits ?? null,
      filters.maxCredits ?? null,
    ],
    queryFn: ({ pageParam }) => catalogApi.courses(buildCourseSearchParams(filters, pageParam)),
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((count, page) => count + page.items.length, 0)
      return loaded < lastPage.total ? loaded : undefined
    },
    placeholderData: (previous) => previous,
  })

  const items = useMemo(
    () => query.data?.pages.flatMap((page) => page.items) ?? [],
    [query.data?.pages],
  )
  const total = query.data?.pages[0]?.total ?? 0
  const hasMore = items.length < total

  const loadMore = useCallback(() => {
    if (query.hasNextPage && !query.isFetchingNextPage) {
      void query.fetchNextPage()
    }
  }, [query])

  return {
    ...query,
    items,
    total,
    hasMore,
    loadMore,
  }
}
