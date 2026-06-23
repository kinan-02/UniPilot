import type { CurriculumGraph, ElectiveBucket, GraduationProgress, RequirementProgressEntry } from '../types/api'

export const PROGRAM_CODE = '009216-1-000'

export function requirementBucket(
  overrides: Partial<RequirementProgressEntry> = {},
): RequirementProgressEntry {
  return {
    requirementGroupId: `${PROGRAM_CODE}:core-math`,
    title: 'Core mathematics',
    isMandatory: true,
    status: 'in_progress',
    minCredits: 12,
    creditsCompleted: 7.5,
    creditsRemaining: 4.5,
    eligibilityEnforcement: 'credit_bucket_only',
    completedCourses: [
      {
        courseId: 'c1',
        courseNumber: '00940345',
        courseTitle: 'Sample course',
        creditsEarned: 7.5,
      },
    ],
    ...overrides,
  }
}

export function electivePool(overrides: Partial<ElectiveBucket> = {}): ElectiveBucket {
  return {
    groupId: `${PROGRAM_CODE}:elective-ds-pool`,
    title: 'DS elective pool',
    linkedCreditBucketId: `${PROGRAM_CODE}:elective-ds`,
    rule: { type: 'course_pool', operator: 'choose_credits' },
    courses: [{ courseNumber: '00940345', title: 'Sample course', credits: 3.5 }],
    courseCount: 1,
    explorerReady: true,
    ...overrides,
  }
}

export function generalTechnionPools(): ElectiveBucket[] {
  return [
    electivePool({
      groupId: `${PROGRAM_CODE}:enrichment-pool`,
      title: 'University enrichment',
      linkedCreditBucketId: `${PROGRAM_CODE}:enrichment`,
      courses: [{ courseNumber: '03940580', title: 'Enrichment', credits: 1.5 }],
    }),
    electivePool({
      groupId: `${PROGRAM_CODE}:free-elective-pool`,
      title: 'Free electives',
      linkedCreditBucketId: `${PROGRAM_CODE}:free-elective`,
      courses: [],
      courseCount: 0,
    }),
    electivePool({
      groupId: `${PROGRAM_CODE}:physical-education-pool`,
      title: 'Physical education',
      linkedCreditBucketId: `${PROGRAM_CODE}:physical-education`,
      courses: [{ courseNumber: '03940800', title: 'PE', credits: 1 }],
    }),
  ]
}

export function baseGraduationProgress(
  overrides: Partial<GraduationProgress> = {},
): GraduationProgress {
  return {
    degreeId: '665f2b0f2a3f7b2a1a9a7d01',
    degreeCode: '006',
    degreeName: 'Industrial Engineering',
    catalogYear: 2025,
    catalogVersion: '2025-2026',
    completedCredits: 7.5,
    totalRequiredCredits: 155,
    creditsRemaining: 147.5,
    completionPercentage: 4.84,
    completedElectiveCredits: 3.5,
    remainingElectiveCredits: 2.5,
    statusSummary: 'in_progress',
    requirementProgress: [
      requirementBucket(),
      requirementBucket({
        requirementGroupId: `${PROGRAM_CODE}:elective-ds`,
        title: 'Data Science electives',
        isMandatory: false,
        minCredits: 6,
        creditsCompleted: 3.5,
        creditsRemaining: 2.5,
        eligibilityEnforcement: 'strict_pool',
        completedCourses: [
          {
            courseId: 'c2',
            courseNumber: '00940411',
            courseTitle: 'Elective sample',
            creditsEarned: 3.5,
          },
        ],
      }),
    ],
    missingRequirements: [],
    assumptions: ['Passing grades above 55 count.'],
    ...overrides,
  }
}

export function emptyCurriculumGraph(
  overrides: Partial<CurriculumGraph> = {},
): CurriculumGraph {
  return {
    trackSlug: 'track-industrial-engineering-management',
    programCode: PROGRAM_CODE,
    catalogYear: 2025,
    catalogVersion: '2025-2026',
    viewDefault: 'semester_swimlanes',
    semesterLanes: [
      {
        semester: 1,
        title: 'Year 1 — Semester 1',
        nodeIds: ['node-discrete-math', 'node-intro-cs'],
        collapsedByDefault: false,
      },
    ],
    nodes: [
      {
        nodeId: 'node-discrete-math',
        courseNumber: '00940345',
        title: 'Discrete Math',
        semester: 1,
        status: 'available',
        credits: { display: '4', value: 4, uncertain: false },
        alternatives: [],
        dataQuality: {
          manualReviewRequired: false,
          confidence: 'high',
          hasAlternatives: false,
          creditsUncertain: false,
          verifyWithRegistrar: false,
        },
        prerequisiteNumbers: [],
        missingPrerequisites: [],
        isBottleneck: false,
      },
      {
        nodeId: 'node-intro-cs',
        courseNumber: '01040031',
        title: 'Intro to CS',
        semester: 1,
        status: 'completed',
        credits: { display: '3.5', value: 3.5, uncertain: false },
        alternatives: [],
        dataQuality: {
          manualReviewRequired: false,
          confidence: 'high',
          hasAlternatives: false,
          creditsUncertain: false,
          verifyWithRegistrar: false,
        },
        prerequisiteNumbers: ['00940345'],
        missingPrerequisites: [],
        isBottleneck: false,
      },
    ],
    edges: [
      {
        from: 'node-discrete-math',
        to: 'node-intro-cs',
        kind: 'prerequisite',
      },
    ],
    bottlenecks: [],
    electiveBuckets: [],
    ...overrides,
  }
}

export function manyPoolCourses(count: number) {
  return Array.from({ length: count }, (_, index) => ({
    courseNumber: String(96040000 + index).padStart(8, '0'),
    title: `Course ${index + 1}`,
    credits: 3,
  }))
}

export const progressT = (key: string) => {
  const labels: Record<string, string> = {
    'progress.electiveExplorer.catalogTitle': 'Elective pools & chains',
    'progress.electiveExplorer.catalogHintSimple':
      'Tap a pool to expand eligible courses inline — no separate panel.',
    'progress.electiveExplorer.searchPools': 'Search pools…',
    'progress.electiveExplorer.generalTechnionPoolsTitle': 'General Technion requirements',
    'progress.electiveExplorer.generalTechnionPoolsHint':
      'University enrichment, free electives, and physical education.',
    'progress.electiveExplorer.noPoolsMatch': 'No pools match "{query}"',
    'progress.electiveExplorer.pools.enrichment-pool': 'University enrichment (CHE)',
    'progress.electiveExplorer.pools.free-elective-pool': 'Free electives',
    'progress.electiveExplorer.pools.physical-education-pool': 'Physical education',
    'progress.electiveExplorer.pools.elective-ds-pool': 'Data science elective pool',
    'progress.electiveExplorer.ruleChooseCredits': 'Meet minimum credits from listed courses',
    'progress.electiveExplorer.countedListed': '{counted} counted · {listed} listed',
    'progress.electiveExplorer.searchCourses': 'Search courses…',
    'progress.electiveExplorer.openCatalog': 'Open catalog',
    'progress.electiveExplorer.showingCourses': 'Showing {visible} of {total}',
  }
  return labels[key] ?? key
}
