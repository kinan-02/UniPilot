const { loadValidatedCatalog } = require("../../src/catalog/loadValidatedCatalog");
const { calculateGraduationProgress } = require("../../src/graduation/graduationProgressCalculator");
const { ObjectId } = require("mongodb");

describe("Technion seed elective pool", () => {
  test("elective requirement pool has enough catalog credits to satisfy minCredits", async () => {
    const catalog = await loadValidatedCatalog({
      institutionId: "technion",
      catalogYear: 2025
    });

    const electiveRequirement = catalog.degreeRequirements.find(
      (requirement) => requirement.requirementType === "elective"
    );
    const coursesById = new Map(catalog.courses.map((course) => [course.id, course]));

    const poolCourseIds = electiveRequirement.courseIds;
    const poolCredits = poolCourseIds.reduce(
      (sum, courseId) => sum + (coursesById.get(courseId)?.credits ?? 0),
      0
    );

    expect(poolCourseIds.length).toBeGreaterThanOrEqual(2);
    expect(poolCredits).toBeGreaterThanOrEqual(electiveRequirement.minCredits);
    expect(
      poolCourseIds.every((courseId) => coursesById.get(courseId)?.metadata?.isCuratedPlaceholder)
    ).toBe(true);
  });

  test("two seeded elective completions can satisfy the elective requirement in graduation progress", async () => {
    const catalog = await loadValidatedCatalog({
      institutionId: "technion",
      catalogYear: 2025
    });

    const degree = catalog.degrees[0];
    const requirements = catalog.degreeRequirements.map((requirement) => ({
      ...requirement,
      _id: new ObjectId(requirement.id),
      degreeId: new ObjectId(requirement.degreeId),
      courseSet: requirement.courseIds.map((courseId) => new ObjectId(courseId))
    }));
    const catalogCourses = catalog.courses.map((course) => ({
      ...course,
      _id: new ObjectId(course.id)
    }));

    const electiveIds = catalog.degreeRequirements.find(
      (requirement) => requirement.requirementType === "elective"
    ).courseIds;

    const progress = calculateGraduationProgress({
      degree: { ...degree, _id: new ObjectId(degree.id) },
      requirements,
      catalogCourses,
      completedCourseRecords: [
        {
          courseId: new ObjectId(electiveIds[0]),
          grade: "B+",
          creditsEarned: 3,
          semesterCode: "2024-1",
          recordedAt: new Date("2024-06-01T00:00:00.000Z")
        },
        {
          courseId: new ObjectId(electiveIds[1]),
          grade: "A-",
          creditsEarned: 3,
          semesterCode: "2024-2",
          recordedAt: new Date("2024-12-01T00:00:00.000Z")
        }
      ]
    });

    const electiveProgress = progress.requirementProgress.find(
      (entry) => entry.requirementType === "elective"
    );

    expect(electiveProgress.status).toBe("satisfied");
    expect(electiveProgress.creditsCompleted).toBe(6);
    expect(progress.completedElectiveCredits).toBe(6);
    expect(progress.remainingElectiveCredits).toBe(0);
  });
});
