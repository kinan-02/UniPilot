const { ObjectId } = require("mongodb");
const { analyzeAcademicRisks } = require("../../src/risk/academicRiskAnalyzer");
const { calculateGraduationProgress } = require("../../src/graduation/graduationProgressCalculator");

const DEGREE_ID = "665f2b0f2a3f7b2a1a9a7d01";
const FOUNDATIONS = "665f2b0f2a3f7b2a1a9a7c01";
const DISCRETE_MATH = "665f2b0f2a3f7b2a1a9a7c02";
const DATA_STRUCTURES = "665f2b0f2a3f7b2a1a9a7c03";
const ALGORITHMS = "665f2b0f2a3f7b2a1a9a7c05";
const MACHINE_LEARNING = "665f2b0f2a3f7b2a1a9a7c07";

function buildCatalogCourse(courseId, { number, title, credits = 3, prerequisites = [], level = "undergraduate", tags = [] } = {}) {
  return {
    _id: new ObjectId(courseId),
    number,
    title,
    credits,
    level,
    tags,
    prerequisites: prerequisites.map((id) => new ObjectId(id))
  };
}

function buildCompletedRecord(courseId, { grade = "B+", creditsEarned = 3 } = {}) {
  return {
    courseId: new ObjectId(courseId),
    grade,
    creditsEarned,
    semesterCode: "2024-1",
    recordedAt: new Date("2024-06-01T00:00:00.000Z")
  };
}

function buildAnalysisContext({ completedCourseRecords = [] } = {}) {
  const degree = {
    _id: new ObjectId(DEGREE_ID),
    code: "CS-BSC",
    name: "BSc CS",
    catalogYear: 2025,
    catalogVersion: "2025.1"
  };

  const catalogCourses = [
    buildCatalogCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" }),
    buildCatalogCourse(DISCRETE_MATH, { number: "02340102", title: "Discrete Math" }),
    buildCatalogCourse(DATA_STRUCTURES, {
      number: "02340201",
      title: "Data Structures",
      prerequisites: [FOUNDATIONS]
    }),
    buildCatalogCourse(ALGORITHMS, {
      number: "02340301",
      title: "Algorithms 1",
      prerequisites: [DATA_STRUCTURES]
    }),
    buildCatalogCourse(MACHINE_LEARNING, {
      number: "02360363",
      title: "Machine Learning",
      prerequisites: [ALGORITHMS],
      tags: ["elective", "ai"]
    })
  ];

  const requirements = [
    {
      _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e01"),
      requirementType: "core",
      title: "Core courses",
      ruleExpression: { type: "course_set", operator: "all_of" },
      minCredits: 24,
      courseSet: [FOUNDATIONS, DISCRETE_MATH, DATA_STRUCTURES, ALGORITHMS].map((id) => new ObjectId(id)),
      priority: 1,
      isMandatory: true
    },
    {
      _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e03"),
      requirementType: "elective",
      title: "Electives",
      ruleExpression: { type: "credit_pool", operator: "min_credits_from_set" },
      minCredits: 6,
      courseSet: [new ObjectId(MACHINE_LEARNING)],
      priority: 3,
      isMandatory: false
    },
    {
      _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e04"),
      requirementType: "credit",
      title: "Total degree credits",
      ruleExpression: { type: "total_credits", operator: "gte" },
      minCredits: 155,
      courseSet: [],
      priority: 4,
      isMandatory: true
    }
  ];

  const graduationProgress = calculateGraduationProgress({
    degree,
    requirements,
    catalogCourses,
    completedCourseRecords
  });

  return {
    profile: {
      preferences: { maxCreditsPerSemester: 12 }
    },
    degree,
    catalogCourses,
    requirements,
    graduationProgress,
    completedCourseRecords
  };
}

function buildPlannedCourse(courseId, { number, title, credits = 3, category = "mandatory" } = {}) {
  return {
    courseId,
    courseNumber: number,
    courseTitle: title,
    credits,
    category,
    reason: "Test planned course"
  };
}

describe("academic risk analyzer", () => {
  test("detects empty plan risk", () => {
    const context = buildAnalysisContext();
    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [],
        maxCredits: 12,
        minCredits: 0,
        explanation: {}
      }
    });

    expect(analysis.summary.totalRisks).toBeGreaterThanOrEqual(1);
    expect(analysis.risks.some((risk) => risk.riskType === "empty_plan")).toBe(true);
    expect(analysis.summary.highestSeverity).toBe("high");
  });

  test("detects credit overload and too few credits", () => {
    const context = buildAnalysisContext();
    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" }),
          buildPlannedCourse(DISCRETE_MATH, { number: "02340102", title: "Discrete Math" }),
          buildPlannedCourse(DATA_STRUCTURES, { number: "02340201", title: "Data Structures" }),
          buildPlannedCourse(ALGORITHMS, { number: "02340301", title: "Algorithms 1" })
        ],
        maxCredits: 9,
        minCredits: 15,
        explanation: {}
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "credit_overload")).toBe(true);
    expect(analysis.risks.some((risk) => risk.riskType === "too_few_credits")).toBe(true);
    expect(analysis.risks.every((risk) => risk.source === "rule")).toBe(true);
  });

  test("detects unmet prerequisites and completed course risks", () => {
    const context = buildAnalysisContext({
      completedCourseRecords: [buildCompletedRecord(FOUNDATIONS)]
    });

    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" }),
          buildPlannedCourse(ALGORITHMS, { number: "02340301", title: "Algorithms 1" })
        ],
        maxCredits: 12,
        minCredits: 0,
        explanation: {}
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "course_already_completed")).toBe(true);
    expect(analysis.risks.some((risk) => risk.riskType === "unmet_prerequisites")).toBe(true);
    const prerequisiteRisk = analysis.risks.find((risk) => risk.riskType === "unmet_prerequisites");
    expect(prerequisiteRisk.evidence.missingPrerequisites.length).toBeGreaterThan(0);
    expect(prerequisiteRisk.suggestedFixes.length).toBeGreaterThan(0);
  });

  test("detects failed course retake warning", () => {
    const context = buildAnalysisContext({
      completedCourseRecords: [buildCompletedRecord(FOUNDATIONS, { grade: "F", creditsEarned: 0 })]
    });

    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" })
        ],
        maxCredits: 12,
        minCredits: 0,
        explanation: {}
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "failed_course_retake")).toBe(true);
  });

  test("detects elective-only plan while mandatory requirements remain", () => {
    const context = buildAnalysisContext();
    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(MACHINE_LEARNING, {
            number: "02360363",
            title: "Machine Learning",
            category: "elective"
          })
        ],
        maxCredits: 12,
        minCredits: 0,
        explanation: {}
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "no_mandatory_progress")).toBe(true);
    expect(analysis.risks.some((risk) => risk.riskType === "unmet_prerequisites")).toBe(true);
  });

  test("includes partial plan risk from persisted planner explanation", () => {
    const context = buildAnalysisContext();
    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" })
        ],
        maxCredits: 12,
        minCredits: 9,
        explanation: {
          partialPlan: true,
          summary: "Partial plan generated because workload limits prevented reaching minCredits"
        }
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "partial_plan")).toBe(true);
  });

  test("detects insufficient graduation progress when plan avoids remaining mandatory courses", () => {
    const context = buildAnalysisContext({
      completedCourseRecords: [buildCompletedRecord(FOUNDATIONS)]
    });

    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations", category: "mandatory" })
        ],
        maxCredits: 12,
        minCredits: 0,
        explanation: {}
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "insufficient_graduation_progress")).toBe(true);
    expect(analysis.risks.some((risk) => risk.riskType === "no_mandatory_progress")).toBe(false);
  });

  test("detects deferred planner warnings from explanation evidence", () => {
    const context = buildAnalysisContext();
    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" })
        ],
        maxCredits: 12,
        minCredits: 0,
        explanation: {
          partialPlan: false,
          blockedByPrerequisites: [
            {
              courseId: DATA_STRUCTURES,
              courseNumber: "02340201",
              courseTitle: "Data Structures"
            }
          ],
          skippedDueToWorkload: [
            {
              courseId: DISCRETE_MATH,
              courseNumber: "02340102",
              courseTitle: "Discrete Math"
            }
          ]
        }
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "deferred_prerequisite_blocked_courses")).toBe(
      true
    );
    expect(analysis.risks.some((risk) => risk.riskType === "deferred_workload_limited_courses")).toBe(
      true
    );
    expect(analysis.contextSnapshot.plannedCourseIds).toEqual([FOUNDATIONS]);
  });

  test("detects duplicate planned courses", () => {
    const context = buildAnalysisContext();
    const analysis = analyzeAcademicRisks({
      ...context,
      planView: {
        semesterCode: "2025-2",
        plannedCourses: [
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" }),
          buildPlannedCourse(FOUNDATIONS, { number: "02340101", title: "Foundations" })
        ],
        maxCredits: 12,
        minCredits: 0,
        explanation: {}
      }
    });

    expect(analysis.risks.some((risk) => risk.riskType === "duplicate_planned_course")).toBe(true);
  });
});
