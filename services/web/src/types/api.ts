export type User = {
  id: string
  email: string
  status: string
}

export type AuthPayload = {
  accessToken: string
  user: User
}

export type StudentProfile = {
  id: string
  userId: string
  institutionId: string
  programType: string
  degreeId: string | null
  catalogYear: number
  currentSemesterCode: string
  preferences?: {
    maxCreditsPerSemester?: number
  }
}

export type CourseSummary = {
  id?: string
  courseNumber: string
  title?: string
  titleHebrew?: string
  faculty?: string
  credits?: number
}

export type PaginatedCourses = {
  items: CourseSummary[]
  total: number
  limit: number
  offset: number
}

export type DegreeProgram = {
  id?: string
  programCode: string
  name?: string
  nameHebrew?: string
  nameEn?: string
  totalCredits?: number
}

export type CompletedCourse = {
  id: string
  courseId: string
  courseNumber?: string
  courseTitle?: string
  semesterCode: string
  grade: string
  creditsEarned: number
  attempt: number
  source: string
}

export type GraduationProgress = {
  degreeId: string
  degreeCode?: string
  degreeName?: string
  completedCredits: number
  totalRequiredCredits: number
  creditsRemaining: number
  completionPercentage: number
  statusSummary: string
  requirementProgress?: Array<{
    requirementGroupId: string
    title?: string
    completedCredits: number
    requiredCredits: number
    status: string
  }>
}

export type CourseOffering = {
  courseNumber: string
  academicYear: number
  semesterCode: number
  semesterName?: string
  scheduleGroups: Array<Record<string, string>>
  instructors?: string
}

export type CourseDetail = CourseSummary & {
  institutionId?: string
  offerings?: CourseOffering[]
}

export type ScheduleSlot = {
  day: string
  timeRange: string
  slotType?: string
  courseNumber?: string
  courseTitle?: string
}

export type WeeklySchedule = {
  status?: string
  entries?: Array<{
    courseId: string
    courseNumber?: string
    courseTitle?: string
    academicYear?: number
    semesterCode?: number
    scheduleGroups?: Array<Record<string, string>>
  }>
  conflicts?: Array<{
    day?: string
    timeRange?: string
    courseNumbers?: string[]
    reason?: string
  }>
  weekView?: Array<{ day: string; slots: ScheduleSlot[] }>
  summary?: string
}

export type PlannedCourse = {
  courseId: string
  courseNumber?: string
  courseTitle?: string
  credits?: number
  category?: string
  reason?: string
}

export type SemesterPlan = {
  id: string
  name?: string
  status: string
  version: number
  plannerType: string
  semesters: Array<{
    semesterCode: string
    goalCredits?: number
    plannedCourses: PlannedCourse[]
    weeklySchedule?: WeeklySchedule
  }>
  explanation?: {
    summary?: string
    partialPlan?: boolean
    emptyPlan?: boolean
    totalRecommendedCredits?: number
  }
}

export type AcademicRiskAnalysis = {
  id: string
  summary?: string
  status?: string
  semesterCode?: string
  risks?: Array<{
    ruleId?: string
    severity?: string
    title?: string
    message?: string
  }>
}
