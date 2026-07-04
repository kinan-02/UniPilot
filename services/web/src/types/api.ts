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
  facultyId?: string | null
  programType: string
  degreeId: string | null
  catalogYear: number
  currentSemesterCode: string
  academicPath?: StudentAcademicPath
  preferences?: {
    maxCreditsPerSemester?: number
  }
}

export type AcademicPathSelection = {
  kind: 'bsc_track' | 'minor' | 'special_program' | 'graduate_program' | 'dne_specialization'
  trackSlug?: string | null
  programCode?: string | null
  label?: string | null
}

export type StudentAcademicPath = {
  trackSlug?: string | null
  minors?: AcademicPathSelection[]
  specialPrograms?: AcademicPathSelection[]
  graduatePrograms?: AcademicPathSelection[]
  specializations?: AcademicPathSelection[]
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
  metadata?: {
    wikiPage?: string
    faculty?: string
    facultyId?: string
    programKind?: string
  }
}

export type CatalogFaculty = {
  id?: string
  facultyId: string
  institutionId: string
  wikiSlug: string
  name?: string
  nameHe?: string
  nameEn?: string
  aliases?: string[]
  catalogPrefix?: string
}

export type CatalogPathOption = {
  id?: string
  optionKey: string
  facultyId: string
  wikiSlug: string
  kind:
    | 'bsc_track'
    | 'special_program'
    | 'minor'
    | 'graduate_program'
    | 'dne_specialization'
    | string
  name?: string
  nameHe?: string
  nameEn?: string
  studyLevels?: string[]
  selectableAsPrimary?: boolean
  linkedProgramCode?: string
  linkedDegreeProgramId?: string
  description?: string
  duration?: string
  totalCreditsRequired?: string
}

export type ParsedTranscriptCourse = {
  courseNumber: string
  semesterCode: string
  grade: number
  creditsEarned: number
  attempt?: number | null
  title?: string | null
  confidence: number
  warnings: string[]
}

export type TranscriptParsePreview = {
  courses: ParsedTranscriptCourse[]
  studentId?: string | null
  studentName?: string | null
  warnings: string[]
  parseMetadata: {
    pageCount: number
    extractor: string
    pipelineVersion: string
    textCharCount: number
    ocrUsed: boolean
  }
}

export type TranscriptImportResult = {
  created: CompletedCourse[]
  skippedDuplicates: string[]
  unresolved: Array<{ courseNumber: string; semesterCode: string; reason: string }>
  createdCount: number
  skippedCount: number
  unresolvedCount: number
}

export type CompletedCourse = {
  id: string
  courseId: string
  courseNumber?: string
  courseTitle?: string
  semesterCode: string
  grade: string
  gradePoints?: number | null
  creditsEarned: number
  attempt: number
  source: string
}

export type CourseProgressEntry = {
  courseId: string
  courseNumber?: string
  courseTitle?: string
  catalogCredits?: number
  creditsEarned?: number
  grade?: string | number
  semesterCode?: string
  assignedPoolGroupId?: string | null
}

export type RequirementProgressEntry = {
  requirementId?: string
  requirementGroupId: string
  title?: string
  requirementType?: string
  isMandatory?: boolean
  requirementEnforcement?: string
  eligibilityEnforcement?: 'strict_pool' | 'credit_bucket_only' | string
  linkedPoolGroupId?: string | null
  status: string
  minCredits: number
  creditsCompleted: number
  creditsRemaining: number
  completedCourses?: CourseProgressEntry[]
  remainingCourses?: CourseProgressEntry[]
}

export type MissingRequirementEntry = {
  requirementId?: string
  requirementGroupId: string
  title?: string
  requirementType?: string
  isMandatory?: boolean
  status: string
  creditsCompleted: number
  creditsRequired: number
  creditsRemaining: number
  remainingCourseCount?: number
  eligibilityEnforcement?: string
}

export type IneligibleCreditEntry = {
  courseId: string
  courseNumber?: string
  creditsEarned: number
  reason?: string
  linkedPoolGroupId?: string
  bucketSuffix?: string
}

export type GraduationProgress = {
  degreeId: string
  degreeCode?: string
  degreeName?: string
  catalogYear?: number
  catalogVersion?: string
  completedCredits: number
  transcriptCreditsTotal?: number
  totalRequiredCredits: number
  creditsRemaining: number
  completionPercentage: number
  completedMandatoryCourses?: CourseProgressEntry[]
  remainingMandatoryCourses?: CourseProgressEntry[]
  completedElectiveCredits?: number
  remainingElectiveCredits?: number
  requirementProgress?: RequirementProgressEntry[]
  missingRequirements?: MissingRequirementEntry[]
  ineligibleCredits?: IneligibleCreditEntry[]
  assumptions?: string[]
  statusSummary: string
}

export type CurriculumCreditsDisplay = {
  display: string
  value: number | null
  uncertain: boolean
  range?: { min: number; max: number } | null
}

export type CurriculumDataQuality = {
  manualReviewRequired: boolean
  confidence: string
  hasAlternatives: boolean
  creditsUncertain: boolean
  verifyWithRegistrar: boolean
  sourceNotes?: string[]
}

export type CurriculumGraphNode = {
  nodeId: string
  courseNumber: string
  title?: string
  semester: number
  credits: CurriculumCreditsDisplay
  alternatives: string[]
  dataQuality: CurriculumDataQuality
  prerequisiteNumbers: string[]
  status:
    | 'completed'
    | 'failed'
    | 'in_progress'
    | 'available'
    | 'blocked'
    | 'verify_with_registrar'
  missingPrerequisites: string[]
  isBottleneck: boolean
  satisfiedViaAlternative?: string
}

export type CurriculumGraphEdge = {
  from: string
  to: string
  kind: 'prerequisite' | 'corequisite' | 'external_prerequisite'
  requirementType?: 'hard' | 'catalog_text' | 'external' | 'corequisite'
  highlight?: string
}

export type ElectiveBucketRule = {
  type: string
  operator?: string | null
  chooseCount?: number | null
  chain?: string | null
  minCredits?: number | null
  allowedPrefixes?: string[]
}

export type ElectivePoolCourse = {
  courseNumber: string
  title?: string
  titleHe?: string
  credits?: number | null
  alternatives?: string[]
  notes?: string[]
}

export type PoolProgressDisplay =
  | 'chain_steps'
  | 'dedicated_bucket_credits'
  | 'shared_bucket_credits'
  | 'none'

export type ElectiveBucket = {
  groupId: string
  title?: string
  requirementType?: string
  minCredits?: number | null
  linkedCreditBucketId?: string | null
  rule: ElectiveBucketRule
  allowedPrefixes?: string[]
  courses: ElectivePoolCourse[]
  courseCount: number
  courseListSource?: 'explicit' | 'prefix_catalog' | 'vault_union' | 'empty'
  progressDisplay?: PoolProgressDisplay
  coursesTruncated?: boolean
  advisoryOnly?: boolean
  manualReviewRequired?: boolean
  notes?: string[]
  catalogDescription?: string | null
  explorerReady?: boolean
}

export type CurriculumGraph = {
  trackSlug: string
  programCode: string
  catalogYear: number
  catalogVersion: string
  viewDefault: 'semester_swimlanes' | 'mind_map'
  semesterLanes: Array<{
    semester: number
    title: string
    nodeIds: string[]
    collapsedByDefault: boolean
    advisoryOnly?: boolean
  }>
  nodes: CurriculumGraphNode[]
  edges: CurriculumGraphEdge[]
  electiveBuckets?: ElectiveBucket[]
  advisories?: Array<{ code: string; severity: string; message: string }>
  bottlenecks: Array<{ courseNumber: string; blockedBy: string[]; reason: string }>
  /** Same course under different track catalog codes (from vault). */
  crossTrackEquivalenceGroups?: string[][]
  transcriptSummary?: {
    completedCount: number
    failedCount: number
    inProgressCount: number
  }
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

export type AcademicRiskSummary = {
  totalRisks: number
  highestSeverity?: 'high' | 'medium' | 'low' | string | null
  counts?: {
    low?: number
    medium?: number
    high?: number
  }
}

export type AcademicRiskAnalysis = {
  id: string
  summary?: AcademicRiskSummary | string
  status?: string
  semesterCode?: string
  risks?: Array<{
    ruleId?: string
    severity?: string
    title?: string
    message?: string
  }>
}

export type SimulationOpType = 'drop_course' | 'add_course' | 'add_planned_course' | 'change_track'

export type SimulationOperation =
  | { type: 'drop_course'; courseNumber: string }
  | { type: 'add_course'; courseNumber: string; grade?: number; semesterCode?: string | null }
  | { type: 'add_planned_course'; courseNumber: string }
  | { type: 'change_track'; trackSlug: string }

export type SimulationScenario = {
  id: string
  name: string
  description?: string | null
  operations: SimulationOperation[]
  semesterCode?: string | null
  planId?: string | null
  naturalLanguagePrompt?: string | null
  status?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

export type SimulationGraduationSnapshot = {
  completedCredits?: number
  totalRequiredCredits?: number
  creditsRemaining?: number
  completionPercentage?: number
  statusSummary?: string
}

export type SimulationSnapshot = {
  graduation?: SimulationGraduationSnapshot
  risk?: Record<string, unknown> | null
  trackSlug?: string | null
}

export type SimulationProgressDelta = {
  completedCreditsDelta?: number
  creditsRemainingDelta?: number
  completionPercentageDelta?: number
}

export type SimulationResult = {
  id: string
  scenarioId: string
  status?: string | null
  beforeSnapshot: SimulationSnapshot
  afterSnapshot: SimulationSnapshot
  deltas: {
    progress?: SimulationProgressDelta
    risk?: Record<string, unknown> | null
  }
  summary?: string | null
  narrative?: string | null
  warnings?: string[]
  jobId?: string | null
  generatedAt?: string | null
  createdAt?: string | null
}

export type SimulationRunResponse =
  | {
      asyncAccepted: false
      simulationResult: SimulationResult
    }
  | {
      asyncAccepted: true
      job: AiJob
    }

export type AdvisorAgentTrace = {
  retrievalAgent: {
    status?: string | null
    iterations?: number | null
    steps?: Array<Record<string, unknown>>
  }
  profileAgentInvocations?: Array<Record<string, unknown>>
  planningAgentInvocations?: Array<Record<string, unknown>>
  regulationAgentInvocations?: Array<Record<string, unknown>>
  retrievalBlocks?: Array<Record<string, unknown>>
  semesterResolution?: Record<string, unknown> | null
}

export type AiJob = {
  id: string
  type: string
  status: 'pending' | 'processing' | 'completed' | 'failed' | string
  payload: Record<string, unknown>
  result?: Record<string, unknown> | null
  error?: string | null
  createdAt?: string | null
  updatedAt?: string | null
  startedAt?: string | null
  finishedAt?: string | null
}

export type AdvisorConversation = {
  id: string
  title: string
  summary: string
  exchangeCount: number
  lastConfidence?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

export type AdvisorReply = {
  question: string
  answer: string
  confidence: 'high' | 'medium' | 'low' | string
  courseIds: string[]
  wikiSlugs: string[]
  sources: string[]
  contacts: string[]
  eligibility?: Record<string, unknown> | null
  semesterResolution?: Record<string, unknown> | null
  retrievalStatus?: string | null
  agentTrace?: AdvisorAgentTrace
}

export type AdvisorAskResponse =
  | {
      asyncAccepted: false
      advisor: AdvisorReply
      conversation?: AdvisorConversation
    }
  | {
      asyncAccepted: true
      offloadReason?: string | null
      job: AiJob
    }
