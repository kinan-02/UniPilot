const { calculateGraduationProgress } = require("../graduation/graduationProgressCalculator");
const { findAllCompletedCoursesByUserId } = require("../models/completedCourseModel");
const { findCourses } = require("../models/courseModel");
const { findDegreeById } = require("../models/degreeModel");
const { findDegreeRequirementsByDegreeId } = require("../models/degreeRequirementModel");
const { findStudentProfileByUserId } = require("../models/studentProfileModel");

async function getGraduationProgressForUser(database, userId) {
  const profile = await findStudentProfileByUserId(database, userId);
  if (!profile) {
    return { status: "profile_not_found" };
  }

  if (!profile.degreeId) {
    return { status: "degree_not_selected" };
  }

  const degreeId = profile.degreeId.toString();
  const degree = await findDegreeById(database, degreeId);
  if (!degree) {
    return { status: "degree_not_found" };
  }

  const [requirements, completedCourseRecords, catalogResult] = await Promise.all([
    findDegreeRequirementsByDegreeId(database, degreeId),
    findAllCompletedCoursesByUserId(database, userId),
    findCourses(database, {
      institutionId: degree.institutionId,
      catalogYear: degree.catalogYear,
      limit: 100
    })
  ]);

  const progress = calculateGraduationProgress({
    degree,
    requirements,
    catalogCourses: catalogResult.courses,
    completedCourseRecords
  });

  return {
    status: "ok",
    progress
  };
}

module.exports = {
  getGraduationProgressForUser
};
