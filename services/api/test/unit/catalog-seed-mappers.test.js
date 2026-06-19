const {
  mapCourseRecord,
  mapDegreeRecord,
  mapDegreeRequirementRecord
} = require("../../src/catalog/seedCatalogIntoDatabase");

describe("catalog seed mappers", () => {
  test("mapDegreeRecord preserves catalog metadata and sourceRefs", () => {
    const mapped = mapDegreeRecord({
      id: "665f2b0f2a3f7b2a1a9a7d01",
      institutionId: "technion",
      code: "CS-BSC",
      name: "BSc Computer Science / Software Engineering",
      version: "2025.1",
      catalogYear: 2025,
      catalogVersion: "2025.1",
      effectiveFrom: "2025-01-01T00:00:00.000Z",
      effectiveTo: null,
      status: "published",
      metadata: { faculty: "Computer Science" },
      sourceRefs: [{ sourceId: "seed-technion-cs-degree-2025" }]
    });

    expect(mapped.code).toBe("CS-BSC");
    expect(mapped.catalogYear).toBe(2025);
    expect(mapped.sourceRefs).toHaveLength(1);
  });

  test("mapCourseRecord maps prerequisite ids to ObjectIds", () => {
    const mapped = mapCourseRecord({
      id: "665f2b0f2a3f7b2a1a9a7c03",
      institutionId: "technion",
      subject: "0234",
      number: "02340201",
      title: "Data Structures",
      credits: 3,
      description: "Trees and hash tables",
      level: "undergraduate",
      tags: ["core"],
      prerequisiteCourseIds: ["665f2b0f2a3f7b2a1a9a7c01"],
      corequisiteCourseIds: [],
      catalogYear: 2025,
      catalogVersion: "2025.1",
      version: "2025.1",
      status: "published",
      metadata: {},
      sourceRefs: []
    });

    expect(mapped.number).toBe("02340201");
    expect(mapped.prerequisites).toHaveLength(1);
    expect(mapped.prerequisites[0].toString()).toBe("665f2b0f2a3f7b2a1a9a7c01");
  });

  test("mapDegreeRequirementRecord maps courseIds to courseSet", () => {
    const mapped = mapDegreeRequirementRecord({
      id: "665f2b0f2a3f7b2a1a9a7e01",
      degreeId: "665f2b0f2a3f7b2a1a9a7d01",
      version: "2025.1",
      catalogYear: 2025,
      catalogVersion: "2025.1",
      requirementType: "core",
      title: "Computer Science core courses",
      ruleExpression: { type: "course_set", operator: "all_of" },
      minCredits: 24,
      courseIds: ["665f2b0f2a3f7b2a1a9a7c01"],
      priority: 1,
      isMandatory: true,
      status: "published",
      metadata: {},
      sourceRefs: []
    });

    expect(mapped.requirementType).toBe("core");
    expect(mapped.courseSet).toHaveLength(1);
  });
});
