const {
  validateCatalogListQuery,
  validateCourseIdParam,
  validateCourseListQuery,
  validateDegreeIdParam
} = require("../../src/validation/catalogQuerySchemas");

describe("catalog query validation", () => {
  test("validateCourseListQuery accepts valid query", () => {
    const result = validateCourseListQuery({
      institutionId: "technion",
      catalogYear: "2025",
      page: "1",
      limit: "20"
    });

    expect(result.success).toBe(true);
    expect(result.data.catalogYear).toBe(2025);
  });

  test("validateCourseListQuery rejects unknown fields", () => {
    const result = validateCourseListQuery({
      institutionId: "technion",
      catalogYear: 2025,
      userId: "malicious"
    });

    expect(result.success).toBe(false);
  });

  test("validateCatalogListQuery rejects invalid catalog year", () => {
    const result = validateCatalogListQuery({
      institutionId: "technion",
      catalogYear: 1800
    });

    expect(result.success).toBe(false);
  });

  test("validateCourseIdParam rejects invalid id", () => {
    const result = validateCourseIdParam({ courseId: "not-an-object-id" });
    expect(result.success).toBe(false);
  });

  test("validateDegreeIdParam accepts valid id", () => {
    const result = validateDegreeIdParam({ degreeId: "665f2b0f2a3f7b2a1a9a7d01" });
    expect(result.success).toBe(true);
  });
});
