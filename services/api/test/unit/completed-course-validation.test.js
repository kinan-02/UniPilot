const {
  validateCreateCompletedCoursePayload,
  validateUpdateCompletedCoursePayload,
  validateCompletedCourseListQuery
} = require("../../src/validation/completedCourseSchemas");

const VALID_COURSE_ID = "665f2b0f2a3f7b2a1a9a7c01";

describe("completed course validation", () => {
  test("validateCreateCompletedCoursePayload accepts valid payload", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "B+",
      gradePoints: 82,
      creditsEarned: 3,
      attempt: 1,
      metadata: {
        notes: "Retake after leave"
      }
    });

    expect(result.success).toBe(true);
  });

  test("validateCreateCompletedCoursePayload rejects invalid grade", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "Excellent",
      creditsEarned: 3
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateCompletedCoursePayload rejects negative creditsEarned", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "A",
      creditsEarned: -1
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateCompletedCoursePayload accepts half-credit increments", () => {
    for (const creditsEarned of [0, 1, 1.5, 2, 2.5, 3, 3.5, 4]) {
      const result = validateCreateCompletedCoursePayload({
        courseId: VALID_COURSE_ID,
        semesterCode: "2024-1",
        grade: "A",
        creditsEarned
      });

      expect(result.success).toBe(true);
    }
  });

  test("validateCreateCompletedCoursePayload rejects non-half-credit increments", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "A",
      creditsEarned: 3.25
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateCompletedCoursePayload rejects creditsEarned above 36", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "A",
      creditsEarned: 36.5
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateCompletedCoursePayload rejects invalid semester code", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "Fall-2024",
      grade: "A",
      creditsEarned: 3
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateCompletedCoursePayload rejects userId in body", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "A",
      creditsEarned: 3,
      userId: "665f2b0f2a3f7b2a1a9a7f99"
    });

    expect(result.success).toBe(false);
  });

  test("validateCreateCompletedCoursePayload rejects non-manual source on create", () => {
    const result = validateCreateCompletedCoursePayload({
      courseId: VALID_COURSE_ID,
      semesterCode: "2024-1",
      grade: "A",
      creditsEarned: 3,
      source: "official"
    });

    expect(result.success).toBe(false);
  });

  test("validateUpdateCompletedCoursePayload rejects empty update", () => {
    const result = validateUpdateCompletedCoursePayload({});
    expect(result.success).toBe(false);
  });

  test("validateUpdateCompletedCoursePayload rejects unknown fields", () => {
    const result = validateUpdateCompletedCoursePayload({
      grade: "A",
      source: "official"
    });

    expect(result.success).toBe(false);
  });

  test("validateCompletedCourseListQuery rejects unknown query fields", () => {
    const result = validateCompletedCourseListQuery({
      page: 1,
      userId: "malicious"
    });

    expect(result.success).toBe(false);
  });
});
