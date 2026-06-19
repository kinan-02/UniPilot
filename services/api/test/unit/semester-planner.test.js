const { ObjectId } = require("mongodb");
const {
  generateDeterministicSemesterPlan,
  prerequisitesMet
} = require("../../src/planning/semesterPlanner");
const { calculateGraduationProgress } = require("../../src/graduation/graduationProgressCalculator");

const DEGREE_ID = "665f2b0f2a3f7b2a1a9a7d01";
const FOUNDATIONS = "665f2b0f2a3f7b2a1a9a7c01";
const DISCRETE_MATH = "665f2b0f2a3f7b2a1a9a7c02";
const DATA_STRUCTURES = "665f2b0f2a3f7b2a1a9a7c03";
const ALGORITHMS = "665f2b0f2a3f7b2a1a9a7c05";
const MACHINE_LEARNING = "665f2b0f2a3f7b2a1a9a7c07";

function buildCatalogCourse(courseId, { number, title, credits = 3, prerequisites = [] } = {}) {
  return {
    _id: new ObjectId(courseId),
    number,
    title,
    credits,
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

function buildSeedLikeContext({ completedCourseRecords = [] } = {}) {
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
      prerequisites: [ALGORITHMS]
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
      preferences: { maxCreditsPerSemester: 18 }
    },
    degree,
    catalogCourses,
    requirements,
    graduationProgress,
    completedCourseRecords
  };
}

describe("semester planner", () => {
  test("prerequisitesMet requires all prerequisite courses to be completed", () => {
    const course = buildCatalogCourse(DATA_STRUCTURES, {
      number: "02340201",
      title: "Data Structures",
      prerequisites: [FOUNDATIONS]
    });
    const completed = new Set([FOUNDATIONS]);

    expect(prerequisitesMet(course, completed)).toBe(true);
    expect(prerequisitesMet(course, new Set())).toBe(false);
  });

  test("recommends mandatory courses with no prerequisites when transcript is empty", () => {
    const context = buildSeedLikeContext();
    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2",
      maxCredits: 6
    });

    const recommendedIds = plan.semesters[0].plannedCourses.map((course) => course.courseId);
    expect(recommendedIds).toContain(FOUNDATIONS);
    expect(recommendedIds).toContain(DISCRETE_MATH);
    expect(recommendedIds).not.toContain(ALGORITHMS);
    expect(plan.explanation.emptyPlan).toBe(false);
  });

  test("does not recommend completed mandatory courses again", () => {
    const context = buildSeedLikeContext({
      completedCourseRecords: [buildCompletedRecord(FOUNDATIONS)]
    });

    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2"
    });

    const recommendedIds = plan.semesters[0].plannedCourses.map((course) => course.courseId);
    expect(recommendedIds).not.toContain(FOUNDATIONS);
    expect(recommendedIds).toContain(DATA_STRUCTURES);
  });

  test("failed attempts do not count as completed", () => {
    const context = buildSeedLikeContext({
      completedCourseRecords: [buildCompletedRecord(FOUNDATIONS, { grade: "F", creditsEarned: 0 })]
    });

    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2"
    });

    const recommendedIds = plan.semesters[0].plannedCourses.map((course) => course.courseId);
    expect(recommendedIds).toContain(FOUNDATIONS);
  });

  test("blocks courses with unmet prerequisites and explains them", () => {
    const context = buildSeedLikeContext();
    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2",
      maxCredits: 3
    });

    const recommendedIds = plan.semesters[0].plannedCourses.map((course) => course.courseId);
    expect(recommendedIds).toEqual([FOUNDATIONS]);
    const blockedEntry = plan.explanation.blockedByPrerequisites.find(
      (entry) => entry.courseId === ALGORITHMS
    );
    expect(blockedEntry).toBeTruthy();
    expect(blockedEntry.missingPrerequisites).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          courseId: DATA_STRUCTURES,
          courseNumber: "02340201"
        })
      ])
    );
    expect(blockedEntry.reason).toMatch(/prerequisite/i);
    expect(
      plan.explanation.skippedDueToWorkload.some((entry) => entry.courseId === DATA_STRUCTURES)
    ).toBe(true);
  });

  test("schedules prerequisite chains within the same semester in dependency order", () => {
    const context = buildSeedLikeContext({
      completedCourseRecords: [buildCompletedRecord(DISCRETE_MATH)]
    });
    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2",
      maxCredits: 6
    });

    const recommendedIds = plan.semesters[0].plannedCourses.map((course) => course.courseId);
    expect(recommendedIds).toEqual([FOUNDATIONS, DATA_STRUCTURES]);
    expect(recommendedIds.indexOf(FOUNDATIONS)).toBeLessThan(recommendedIds.indexOf(DATA_STRUCTURES));
  });

  test("uses profile preferred workload when maxCredits is omitted", () => {
    const context = buildSeedLikeContext();
    context.profile.preferences.maxCreditsPerSemester = 6;

    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2"
    });

    expect(plan.explanation.maxCredits).toBe(6);
    expect(plan.explanation.totalRecommendedCredits).toBe(6);
  });

  test("marks partial plan when maxCredits cannot be fully utilized", () => {
    const context = buildSeedLikeContext();
    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2",
      maxCredits: 18
    });

    expect(plan.explanation.partialPlan).toBe(true);
    expect(plan.explanation.summary).toMatch(/maxCredits/i);
  });

  test("returns partial plan when minCredits cannot be reached within maxCredits", () => {
    const context = buildSeedLikeContext();
    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2",
      maxCredits: 3,
      minCredits: 6
    });

    expect(plan.explanation.partialPlan).toBe(true);
    expect(plan.explanation.meetsMinCredits).toBe(false);
    expect(plan.explanation.totalRecommendedCredits).toBe(3);
  });

  test("returns empty plan when workload capacity is zero", () => {
    const context = buildSeedLikeContext();

    const plan = generateDeterministicSemesterPlan({
      ...context,
      semesterCode: "2025-2",
      maxCredits: 0
    });

    expect(plan.explanation.emptyPlan).toBe(true);
    expect(plan.semesters[0].plannedCourses).toEqual([]);
    expect(plan.explanation.summary).toMatch(/no eligible courses/i);
  });
});
