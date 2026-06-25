import { useQuery, type QueryClient, type UseQueryOptions } from '@tanstack/react-query'
import { profileApi } from '../api/endpoints'
import { resetAuthScopedQueryCache } from './authQueryCache'
import { isAuthError, useAuth } from '../auth/AuthContext'
import type { StudentProfile } from '../types/api'

export const STUDENT_PROFILE_QUERY_KEY = ['profile'] as const

export type StudentProfileQueryData = { profile: StudentProfile } | null

export async function fetchStudentProfileOrNull(): Promise<StudentProfileQueryData> {
  try {
    return await profileApi.get()
  } catch (err) {
    if (isAuthError(err) && err.status === 404) {
      return null
    }
    throw err
  }
}

export function studentProfileQueryOptions(
  userId: string | undefined,
): UseQueryOptions<
  StudentProfileQueryData,
  Error,
  StudentProfileQueryData,
  readonly ['profile', string | undefined]
> {
  return {
    queryKey: [...STUDENT_PROFILE_QUERY_KEY, userId],
    queryFn: fetchStudentProfileOrNull,
    enabled: Boolean(userId),
    retry: false,
    staleTime: 0,
  }
}

export function useStudentProfileQuery() {
  const { user } = useAuth()
  return useQuery(studentProfileQueryOptions(user?.id))
}

export function hasStudentProfile(
  data: StudentProfileQueryData | undefined,
): data is { profile: StudentProfile } {
  return Boolean(data?.profile)
}

export function resetStudentProfileCache(queryClient: QueryClient) {
  resetAuthScopedQueryCache(queryClient)
}

export async function invalidateStudentProfile(queryClient: QueryClient) {
  await queryClient.invalidateQueries({ queryKey: STUDENT_PROFILE_QUERY_KEY })
}
