import { apiRequest } from '../lib/api'
import type {
  AcademicRiskAnalysis,
  AuthPayload,
  CompletedCourse,
  CourseDetail,
  CourseOffering,
  DegreeProgram,
  GraduationProgress,
  CurriculumGraph,
  PaginatedCourses,
  SemesterPlan,
  StudentProfile,
  User,
} from '../types/api'

export const authApi = {
  register: (email: string, password: string) =>
    apiRequest<AuthPayload>('/auth/register', {
      method: 'POST',
      body: { email, password },
      token: null,
    }),
  login: (email: string, password: string) =>
    apiRequest<AuthPayload>('/auth/login', {
      method: 'POST',
      body: { email, password },
      token: null,
    }),
  me: () => apiRequest<{ user: User }>('/auth/me'),
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
  degreePrograms: () =>
    apiRequest<{ items: DegreeProgram[]; total: number }>('/catalog/degree-programs'),
}

export const transcriptApi = {
  list: () =>
    apiRequest<{ completedCourses: CompletedCourse[]; pagination: { total: number } }>(
      '/completed-courses',
    ),
  create: (body: Record<string, unknown>) =>
    apiRequest<{ completedCourse: CompletedCourse }>('/completed-courses', {
      method: 'POST',
      body,
    }),
  remove: (id: string) =>
    apiRequest<{ deleted: boolean }>(`/completed-courses/${id}`, { method: 'DELETE' }),
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
