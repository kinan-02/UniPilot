const { createCompletedCourse } = require("../../src/models/completedCourseModel");

async function insertCompletedCourseForTests(database, userId, recordData) {
  return createCompletedCourse(database, userId, recordData);
}

async function insertOfficialCompletedCourseForTests(database, userId, recordData) {
  return createCompletedCourse(database, userId, {
    ...recordData,
    source: "official"
  });
}

function buildCompletedCoursePayload(overrides = {}) {
  return {
    courseId: "665f2b0f2a3f7b2a1a9a7c01",
    semesterCode: "2024-1",
    grade: "B+",
    gradePoints: 82,
    creditsEarned: 3,
    attempt: 1,
    ...overrides
  };
}

module.exports = {
  buildCompletedCoursePayload,
  insertCompletedCourseForTests,
  insertOfficialCompletedCourseForTests
};
