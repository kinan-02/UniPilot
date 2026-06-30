import { apiRequest, apiUpload, getApiBaseUrl } from '../lib/api'
import type {
  AcademicRiskAnalysis,
  AdvisorReply,
  AuthPayload,
  CatalogFaculty,
  CatalogPathOption,
  CompletedCourse,
  CourseDetail,
  CourseOffering,
  DegreeProgram,
  ExamSummary,
  GraduationProgress,
  CurriculumGraph,
  PaginatedCourses,
  ParsedTranscriptCourse,
  PlannedCourse,
  SelectedLessonEvent,
  SemesterPlan,
  StudentProfile,
  TranscriptImportResult,
  TranscriptParsePreview,
  User,
} from '../types/api'

export const authApi = {
  providers: () => apiRequest<{ google: boolean }>('/auth/providers'),
  register: (email: string, password: string) =>
    apiRequest<AuthPayload>('/auth/register', {
      method: 'POST',
      body: { email, password },
      token: null,
    }),
  login: (email: string, password: string, rememberMe = false) =>
    apiRequest<AuthPayload>('/auth/login', {
      method: 'POST',
      body: { email, password, rememberMe },
      token: null,
    }),
  me: () => apiRequest<{ user: User }>('/auth/me'),
}

export function googleSignInUrl(rememberMe: boolean): string {
  const params = new URLSearchParams({ rememberMe: String(rememberMe) })
  return `${getApiBaseUrl()}/auth/google?${params}`
}

export const profileApi = {
  get: () => apiRequest<{ profile: StudentProfile }>('/student-profile'),
  create: (body: Record<string, unknown>) =>
    apiRequest<{ profile: StudentProfile }>('/student-profile', {
      method: 'POST',
      body,
    }),
  update: (body: Record<string, unknown>) =>
    apiRequest<{ profile: StudentProfile }>('/student-profile', {
      method: 'PUT',
      body,
    }),
}

export const catalogApi = {
  courses: (params: Record<string, string | number | boolean>) => {
    const query = new URLSearchParams()
    Object.entries(params).forEach(([key, value]) => {
      if (value !== '' && value !== undefined) query.set(key, String(value))
    })
    return apiRequest<PaginatedCourses>(`/catalog/courses?${query}`)
  },
  course: (courseNumber: string, includeOfferings = false) =>
    apiRequest<{ course: CourseDetail }>(
      `/catalog/courses/${courseNumber}?includeOfferings=${includeOfferings}`,
    ),
  offerings: (
    courseNumber: string,
    params?: { academicYear?: number; semesterCode?: number },
  ) => {
    const query = new URLSearchParams()
    if (params?.academicYear) query.set('academicYear', String(params.academicYear))
    if (params?.semesterCode) query.set('semesterCode', String(params.semesterCode))
    const suffix = query.toString() ? `?${query}` : ''
    return apiRequest<{ courseNumber: string; offerings: CourseOffering[]; total: number }>(
      `/catalog/courses/${courseNumber}/offerings${suffix}`,
    )
  },
  offeringsBatch: (
    courseNumbers: string[],
    params?: { academicYear?: number; semesterCode?: number },
  ) => {
    const query = new URLSearchParams()
    query.set('courseNumbers', courseNumbers.join(','))
    if (params?.academicYear) query.set('academicYear', String(params.academicYear))
    if (params?.semesterCode) query.set('semesterCode', String(params.semesterCode))
    return apiRequest<{
      offeringsByCourseNumber: Record<string, CourseOffering[]>
      totalCourses: number
    }>(`/catalog/offerings?${query}`)
  },
  degreePrograms: (params?: { facultyId?: string; programType?: string }) => {
    const query = new URLSearchParams()
    if (params?.facultyId) query.set('facultyId', params.facultyId)
    if (params?.programType) query.set('programType', params.programType)
    const suffix = query.toString() ? `?${query}` : ''
    return apiRequest<{ items: DegreeProgram[]; total: number }>(`/catalog/degree-programs${suffix}`)
  },
  academicFaculties: (institutionId = 'technion', programType?: string) => {
    const query = new URLSearchParams()
    query.set('institutionId', institutionId)
    if (programType) query.set('programType', programType)
    return apiRequest<{ items: CatalogFaculty[]; total: number }>(
      `/catalog/academic-faculties?${query}`,
    )
  },
  pathOptions: (params: {
    facultyId?: string
    programType?: string
    kind?: string
    primaryOnly?: boolean
  }) => {
    const query = new URLSearchParams()
    if (params.facultyId) query.set('facultyId', params.facultyId)
    if (params.programType) query.set('programType', params.programType)
    if (params.kind) query.set('kind', params.kind)
    if (params.primaryOnly !== undefined) query.set('primaryOnly', String(params.primaryOnly))
    const suffix = query.toString() ? `?${query}` : ''
    return apiRequest<{ items: CatalogPathOption[]; total: number }>(`/catalog/path-options${suffix}`)
  },
  faculties: () => apiRequest<{ items: string[]; total: number }>('/catalog/faculties'),
  plannerSemesters: () =>
    apiRequest<{ planSemesterCodes: string[]; total: number }>('/catalog/planner-semesters'),
}

export const transcriptApi = {
  list: (params?: { page?: number; limit?: number }) => {
    const query = new URLSearchParams()
    if (params?.page) query.set('page', String(params.page))
    if (params?.limit) query.set('limit', String(params.limit))
    const suffix = query.toString() ? `?${query}` : ''
    return apiRequest<{
      completedCourses: CompletedCourse[]
      pagination: { total: number; page: number; limit: number }
    }>(`/completed-courses${suffix}`)
  },
  listAll: async () => {
    const limit = 100
    let page = 1
    let completedCourses: CompletedCourse[] = []
    let total = 0

    while (true) {
      const response = await transcriptApi.list({ page, limit })
      completedCourses = [...completedCourses, ...response.completedCourses]
      total = response.pagination.total
      if (completedCourses.length >= total || response.completedCourses.length === 0) {
        break
      }
      page += 1
    }

    return {
      completedCourses,
      pagination: { total, page: 1, limit: completedCourses.length },
    }
  },
  create: (body: Record<string, unknown>) =>
    apiRequest<{ completedCourse: CompletedCourse }>('/completed-courses', {
      method: 'POST',
      body,
    }),
  remove: (id: string) =>
    apiRequest<{ deleted: boolean }>(`/completed-courses/${id}`, { method: 'DELETE' }),
}

export const transcriptImportApi = {
  parse: (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiUpload<{ parsePreview: TranscriptParsePreview }>('/transcript-import/parse', formData)
  },
  commit: (courses: ParsedTranscriptCourse[]) =>
    apiRequest<{ importResult: TranscriptImportResult }>('/transcript-import/commit', {
      method: 'POST',
      body: {
        courses: courses.map((course) => ({
          courseNumber: course.courseNumber,
          semesterCode: course.semesterCode,
          grade: course.grade,
          creditsEarned: course.creditsEarned,
          attempt: course.attempt ?? 1,
          title: course.title ?? undefined,
        })),
        skipDuplicates: true,
      },
    }),
}

export const progressApi = {
  get: () =>
    apiRequest<{ graduationProgress: GraduationProgress }>('/graduation-progress'),
  curriculumGraph: () =>
    apiRequest<{ curriculumGraph: CurriculumGraph }>(
      '/graduation-progress/curriculum-graph',
    ),
}

export const plansApi = {
  list: () =>
    apiRequest<{ semesterPlans: SemesterPlan[]; pagination: { total: number } }>(
      '/semester-plans',
    ),
  get: (id: string) => apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${id}`),
  create: (body: Record<string, unknown>) =>
    apiRequest<{ semesterPlan: SemesterPlan }>('/semester-plans', {
      method: 'POST',
      body,
    }),
  update: (id: string, body: Record<string, unknown>) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${id}`, {
      method: 'PUT',
      body,
    }),
  archive: (id: string) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${id}`, {
      method: 'DELETE',
    }),
  generate: (body: Record<string, unknown>) =>
    apiRequest<{ semesterPlan: SemesterPlan }>('/semester-plans/generate', {
      method: 'POST',
      body,
    }),
  suggestCourses: (body: Record<string, unknown>) =>
    apiRequest<{
      plannedCourses: PlannedCourse[]
      explanation: Record<string, unknown>
    }>('/semester-plans/suggest-courses', {
      method: 'POST',
      body,
    }),
  suggestSchedule: (body: Record<string, unknown>) =>
    apiRequest<{
      selections: Array<{ courseNumber: string; selectedLessonEvents: SelectedLessonEvent[] }>
      skippedCourses: Array<{ courseNumber?: string; reason?: string }>
      examSummary?: ExamSummary
    }>('/semester-plans/suggest-schedule', {
      method: 'POST',
      body,
    }),
  forkVersion: (id: string, name?: string) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${id}/versions`, {
      method: 'POST',
      body: name ? { name } : {},
    }),
  patchCourse: (planId: string, courseNumber: string, body: Record<string, unknown>) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(
      `/semester-plans/${planId}/courses/${courseNumber}`,
      { method: 'PATCH', body },
    ),
  patchLessonSelection: (planId: string, courseNumber: string, body: Record<string, unknown>) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(
      `/semester-plans/${planId}/courses/${courseNumber}/lesson-selection`,
      { method: 'PATCH', body },
    ),
  patchMaybeCourses: (planId: string, maybeCourses: Record<string, unknown>[]) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${planId}/maybe-courses`, {
      method: 'PATCH',
      body: { maybeCourses },
    }),
  patchMaybeLessonSelection: (planId: string, courseNumber: string, body: Record<string, unknown>) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(
      `/semester-plans/${planId}/maybe-courses/${courseNumber}/lesson-selection`,
      { method: 'PATCH', body },
    ),
  reorderCourses: (planId: string, courseIds: string[]) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${planId}/courses/order`, {
      method: 'PUT',
      body: { courseIds },
    }),
  updateShare: (planId: string, shareEnabled: boolean) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/${planId}/share`, {
      method: 'PATCH',
      body: { shareEnabled },
    }),
  getShared: (shareToken: string) =>
    apiRequest<{ semesterPlan: SemesterPlan }>(`/semester-plans/shared/${shareToken}`, {
      token: null,
    }),
}

export const advisorApi = {
  ask: (question: string) =>
    apiRequest<{ advisor: AdvisorReply }>('/advisor/ask', {
      method: 'POST',
      body: { question },
    }),
}

export const risksApi = {
  list: () =>
    apiRequest<{ academicRiskAnalyses: AcademicRiskAnalysis[]; pagination: { total: number } }>(
      '/academic-risks',
    ),
  analyze: (planId: string) =>
    apiRequest<{ academicRiskAnalysis: AcademicRiskAnalysis }>('/academic-risks/analyze', {
      method: 'POST',
      body: { planId },
    }),
  get: (id: string) =>
    apiRequest<{ academicRiskAnalysis: AcademicRiskAnalysis }>(`/academic-risks/${id}`),
}
