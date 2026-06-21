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
  semesterOfferingSummary?: {
    academicYear: number
    semesterCode: number
    slotTypes?: string[]
    instructors?: string
  }
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
  examDates?: Record<string, string | null>
}

export type CourseDetail = CourseSummary & {
  institutionId?: string
  syllabus?: string
  prerequisitesText?: string
  corequisitesText?: string
  noAdditionalCreditText?: string
  instructors?: string
  notes?: string
  offerings?: CourseOffering[]
}

export type SelectedLessonEvent = {
  eventId: string
  type: string
  group?: string | null
}

export type SelectedGroups = {
  lecture?: number | string | string[] | null
  tutorial?: number | string | string[] | null
  lab?: number | string | string[] | null
  project?: number | string | string[] | null
}

export type CustomEvent = {
  id?: string
  title: string
  day: string
  startTime: string
  endTime: string
  notes?: string
  color?: string
}

export type ExamSummaryItem = {
  courseNumber: string
  courseName?: string
  moed?: string | null
  date?: string | null
  startTime?: string | null
  endTime?: string | null
  raw?: string | null
  isMissing?: boolean
}

export type ExamSummary = {
  exams: ExamSummaryItem[]
  warnings?: Array<{
    type?: string
    date?: string
    courseNumbers?: string[]
    courseNumber?: string
    message?: string
  }>
  totalExams?: number
  missingCount?: number
}
export type PlannerInsights = {
  totalCredits?: number
  activeCourseCount?: number
  totalCourseCount?: number
  maxCreditsPerSemester?: number
  creditsWarning?: {
    status?: string
    message?: string
    totalCredits?: number
    maxCreditsPerSemester?: number
  }
  courseWarnings?: Array<{
    courseId?: string
    courseNumber?: string
    status?: string
    message?: string
    prerequisitesText?: string
    missingPrerequisiteNumbers?: string[]
  }>
  scheduleConflicts?: WeeklySchedule['conflicts']
  scheduleStatus?: string
  examSummary?: ExamSummary
  staleCourseWarnings?: Array<{
    courseNumber?: string
    courseId?: string
    status?: string
    message?: string
  }>
  lessonSelectionWarnings?: Array<{
    courseNumber?: string
    courseId?: string
    type?: string
    eventId?: string
    message?: string
  }>
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
  customEvents?: CustomEvent[]
}

export type PlannedCourse = {
  courseId: string
  courseNumber?: string
  courseTitle?: string
  credits?: number
  category?: string
  reason?: string
  isActive?: boolean
  selectedGroups?: SelectedGroups
  selectedLessonEvents?: SelectedLessonEvent[]
  notes?: string
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
    maybeCourses?: PlannedCourse[]
    weeklySchedule?: WeeklySchedule
    customEvents?: CustomEvent[]
  }>
  explanation?: {
    summary?: string
    partialPlan?: boolean
    emptyPlan?: boolean
    totalRecommendedCredits?: number
  }
  plannerInsights?: PlannerInsights
  shareEnabled?: boolean
  shareToken?: string | null
  readOnly?: boolean
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
