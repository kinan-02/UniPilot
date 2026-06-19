const { toPublicCourse } = require("../../src/models/courseModel");
const { toPublicDegree } = require("../../src/models/degreeModel");
const { toPublicDegreeRequirement } = require("../../src/models/degreeRequirementModel");
const { ObjectId } = require("mongodb");

describe("catalog public mappers", () => {
  test("toPublicCourse exposes catalog metadata and prerequisite ids", () => {
    const course = toPublicCourse({
      _id: new ObjectId("665f2b0f2a3f7b2a1a9a7c03"),
      institutionId: "technion",
      subject: "0234",
      number: "02340201",
      title: "Data Structures",
      credits: 3,
      description: "desc",
      level: "undergraduate",
      tags: ["core"],
      prerequisites: [new ObjectId("665f2b0f2a3f7b2a1a9a7c01")],
      corequisites: [],
      catalogYear: 2025,
      catalogVersion: "2025.1",
      version: "2025.1",
      status: "published",
      metadata: { faculty: "Computer Science" },
      sourceRefs: [{ sourceId: "seed" }],
      createdAt: new Date(),
      updatedAt: new Date()
    });

    expect(course.number).toBe("02340201");
    expect(course.prerequisiteIds).toEqual(["665f2b0f2a3f7b2a1a9a7c01"]);
    expect(course.sourceRefs).toHaveLength(1);
  });

  test("toPublicDegree exposes version and catalog fields", () => {
    const degree = toPublicDegree({
      _id: new ObjectId("665f2b0f2a3f7b2a1a9a7d01"),
      institutionId: "technion",
      code: "CS-BSC",
      name: "BSc Computer Science / Software Engineering",
      version: "2025.1",
      catalogYear: 2025,
      catalogVersion: "2025.1",
      effectiveFrom: new Date(),
      effectiveTo: null,
      status: "published",
      metadata: {},
      sourceRefs: [],
      createdAt: new Date(),
      updatedAt: new Date()
    });

    expect(degree.code).toBe("CS-BSC");
    expect(degree.catalogVersion).toBe("2025.1");
  });

  test("toPublicDegreeRequirement maps courseSet to courseIds", () => {
    const requirement = toPublicDegreeRequirement({
      _id: new ObjectId("665f2b0f2a3f7b2a1a9a7e01"),
      degreeId: new ObjectId("665f2b0f2a3f7b2a1a9a7d01"),
      version: "2025.1",
      catalogYear: 2025,
      catalogVersion: "2025.1",
      requirementType: "core",
      title: "Computer Science core courses",
      ruleExpression: { type: "course_set" },
      minCredits: 24,
      courseSet: [new ObjectId("665f2b0f2a3f7b2a1a9a7c01")],
      priority: 1,
      isMandatory: true,
      status: "published",
      metadata: {},
      sourceRefs: [],
      createdAt: new Date(),
      updatedAt: new Date()
    });

    expect(requirement.courseIds).toEqual(["665f2b0f2a3f7b2a1a9a7c01"]);
  });
});
