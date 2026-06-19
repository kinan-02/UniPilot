const {
  validateCreateStudentProfilePayload,
  validateUpdateStudentProfilePayload
} = require("../../src/validation/studentProfileSchemas");

describe("student profile validation", () => {
  test("validateCreateStudentProfilePayload accepts valid payload", () => {
    const result = validateCreateStudentProfilePayload({
      institutionId: "uni-main",
      programType: "BSc",
      degreeId: "665f2b0f2a3f7b2a1a9a7f11",
      catalogYear: 2025,
      currentSemesterCode: "2025-1",
      preferences: {
        maxCreditsPerSemester: 18
      }
    });

    expect(result.success).toBe(true);
  });

  test("validateCreateStudentProfilePayload rejects invalid semester code", () => {
    const result = validateCreateStudentProfilePayload({
      institutionId: "uni-main",
      programType: "BSc",
      catalogYear: 2025,
      currentSemesterCode: "Fall-2025"
    });

    expect(result.success).toBe(false);
  });

  test("validateUpdateStudentProfilePayload rejects empty update payload", () => {
    const result = validateUpdateStudentProfilePayload({});
    expect(result.success).toBe(false);
  });

  test("validateUpdateStudentProfilePayload rejects unknown fields", () => {
    const result = validateUpdateStudentProfilePayload({
      institutionId: "uni-main",
      userId: "malicious-user-id"
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateStudentProfilePayload rejects unknown fields", () => {
    const result = validateCreateStudentProfilePayload({
      institutionId: "uni-main",
      programType: "BSc",
      catalogYear: 2025,
      currentSemesterCode: "2025-1",
      userId: "malicious-user-id"
    });

    expect(result.success).toBe(false);
  });

  test("validateUpdateStudentProfilePayload rejects _id field", () => {
    const result = validateUpdateStudentProfilePayload({
      _id: "665f2b0f2a3f7b2a1a9a7f11",
      programType: "BSc-Honors"
    });

    expect(result.success).toBe(false);
  });
});
