const { ObjectId } = require("mongodb");
const {
  buildEffectiveCompletions,
  calculateGraduationProgress,
  evaluateRequirement,
  isPassingGrade,
  roundCredits
} = require("../../src/graduation/graduationProgressCalculator");

const DEGREE_ID = "665f2b0f2a3f7b2a1a9a7d01";
const CORE_COURSE_A = "665f2b0f2a3f7b2a1a9a7c01";
const CORE_COURSE_B = "665f2b0f2a3f7b2a1a9a7c02";
const ELECTIVE_COURSE = "665f2b0f2a3f7b2a1a9a7c07";
const MATH_COURSE = "665f2b0f2a3f7b2a1a9a7c09";

function buildRequirement(overrides = {}) {
  return {
    _id: new ObjectId(),
    degreeId: new ObjectId(DEGREE_ID),
    requirementType: "core",
    title: "Test requirement",
    ruleExpression: { type: "course_set", operator: "all_of" },
    minCredits: 6,
    courseSet: [],
    priority: 1,
    isMandatory: true,
    ...overrides
  };
}

function buildCatalogCourse(courseId, credits, title) {
  return {
    _id: new ObjectId(courseId),
    number: `C-${courseId.slice(-2)}`,
    title,
    credits
  };
}

function buildCompletedRecord(courseId, { grade = "B+", creditsEarned = 3, attempt = 1 } = {}) {
  return {
    courseId: new ObjectId(courseId),
    grade,
    creditsEarned,
    semesterCode: "2024-1",
    attempt,
    recordedAt: new Date("2024-06-01T00:00:00.000Z")
  };
}

describe("graduation progress calculator", () => {
  test("isPassingGrade accepts passing grades and rejects failing grades", () => {
    expect(isPassingGrade("B+")).toBe(true);
    expect(isPassingGrade("Pass")).toBe(true);
    expect(isPassingGrade("F")).toBe(false);
    expect(isPassingGrade("Fail")).toBe(false);
  });

  test("roundCredits supports fractional half credits", () => {
    expect(roundCredits(3.5)).toBe(3.5);
    expect(roundCredits(1.5 + 2)).toBe(3.5);
  });

  test("buildEffectiveCompletions ignores failing grades and keeps best passing attempt", () => {
    const completions = buildEffectiveCompletions([
      buildCompletedRecord(CORE_COURSE_A, { grade: "F", creditsEarned: 0, attempt: 1 }),
      buildCompletedRecord(CORE_COURSE_A, { grade: "B", creditsEarned: 3.5, attempt: 2 })
    ]);

    expect(completions.size).toBe(1);
    expect(completions.get(CORE_COURSE_A).creditsEarned).toBe(3.5);
  });

  test("evaluateRequirement marks course_set all_of as satisfied only when every course is completed", () => {
    const requirement = buildRequirement({
      courseSet: [new ObjectId(CORE_COURSE_A), new ObjectId(CORE_COURSE_B)]
    });
    const coursesById = new Map([
      [CORE_COURSE_A, buildCatalogCourse(CORE_COURSE_A, 3, "Course A")],
      [CORE_COURSE_B, buildCatalogCourse(CORE_COURSE_B, 3, "Course B")]
    ]);
    const effectiveCompletions = buildEffectiveCompletions([
      buildCompletedRecord(CORE_COURSE_A, { creditsEarned: 3 })
    ]);

    const progress = evaluateRequirement(requirement, effectiveCompletions, coursesById);

    expect(progress.status).toBe("in_progress");
    expect(progress.completedCourses).toHaveLength(1);
    expect(progress.remainingCourses).toHaveLength(1);
  });

  test("calculateGraduationProgress aggregates mandatory, elective, and total credit progress", () => {
    const degree = {
      _id: new ObjectId(DEGREE_ID),
      code: "CS-BSC",
      name: "BSc CS",
      catalogYear: 2025,
      catalogVersion: "2025.1",
      metadata: { totalCredits: 10 }
    };

    const requirements = [
      buildRequirement({
        _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e01"),
        title: "Core courses",
        courseSet: [new ObjectId(CORE_COURSE_A)],
        minCredits: 3,
        priority: 1
      }),
      buildRequirement({
        _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e03"),
        title: "Electives",
        requirementType: "elective",
        ruleExpression: { type: "credit_pool", operator: "min_credits_from_set" },
        courseSet: [new ObjectId(ELECTIVE_COURSE)],
        minCredits: 6,
        isMandatory: false,
        priority: 3
      }),
      buildRequirement({
        _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e04"),
        title: "Total degree credits",
        requirementType: "credit",
        ruleExpression: { type: "total_credits", operator: "gte" },
        courseSet: [],
        minCredits: 10,
        priority: 4
      })
    ];

    const catalogCourses = [
      buildCatalogCourse(CORE_COURSE_A, 3, "Core A"),
      buildCatalogCourse(ELECTIVE_COURSE, 3, "Elective")
    ];

    const progress = calculateGraduationProgress({
      degree,
      requirements,
      catalogCourses,
      completedCourseRecords: [
        buildCompletedRecord(CORE_COURSE_A, { creditsEarned: 3 }),
        buildCompletedRecord(ELECTIVE_COURSE, { creditsEarned: 3.5 })
      ]
    });

    expect(progress.completedCredits).toBe(6.5);
    expect(progress.totalRequiredCredits).toBe(10);
    expect(progress.completionPercentage).toBe(65);
    expect(progress.completedMandatoryCourses).toHaveLength(1);
    expect(progress.remainingMandatoryCourses).toHaveLength(0);
    expect(progress.completedElectiveCredits).toBe(3.5);
    expect(progress.remainingElectiveCredits).toBe(2.5);
    expect(progress.missingRequirements.length).toBeGreaterThan(0);
    expect(progress.statusSummary).toBe("in_progress");
  });
});
