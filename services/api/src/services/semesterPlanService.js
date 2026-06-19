const { generateDeterministicSemesterPlan } = require("../planning/semesterPlanner");
const { calculateGraduationProgress } = require("../graduation/graduationProgressCalculator");
const { findAllCompletedCoursesByUserId } = require("../models/completedCourseModel");
const { findCourses } = require("../models/courseModel");
const { findDegreeById } = require("../models/degreeModel");
const { findDegreeRequirementsByDegreeId } = require("../models/degreeRequirementModel");
const {
  createSemesterPlan,
  findSemesterPlanByIdAndUserId,
  findSemesterPlansByUserId
} = require("../models/semesterPlanModel");
const { findStudentProfileByUserId } = require("../models/studentProfileModel");

async function loadPlanningContext(database, userId) {
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

  const graduationProgress = calculateGraduationProgress({
    degree,
    requirements,
    catalogCourses: catalogResult.courses,
    completedCourseRecords
  });

  return {
    status: "ok",
    profile,
    degree,
    requirements,
    catalogCourses: catalogResult.courses,
    completedCourseRecords,
    graduationProgress
  };
}

async function generateAndStoreSemesterPlan(database, userId, options) {
  const context = await loadPlanningContext(database, userId);
  if (context.status !== "ok") {
    return context;
  }

  const planData = generateDeterministicSemesterPlan({
    profile: context.profile,
    degree: context.degree,
    catalogCourses: context.catalogCourses,
    requirements: context.requirements,
    graduationProgress: context.graduationProgress,
    completedCourseRecords: context.completedCourseRecords,
    semesterCode: options.semesterCode,
    maxCredits: options.maxCredits,
    minCredits: options.minCredits,
    name: options.name
  });

  const storedPlan = await createSemesterPlan(database, userId, planData);

  return {
    status: "ok",
    plan: storedPlan
  };
}

async function listSemesterPlansForUser(database, userId, pagination) {
  return findSemesterPlansByUserId(database, userId, pagination);
}

async function getSemesterPlanForUser(database, userId, planId) {
  const plan = await findSemesterPlanByIdAndUserId(database, planId, userId);
  if (!plan) {
    return { status: "not_found" };
  }

  return {
    status: "ok",
    plan
  };
}

module.exports = {
  generateAndStoreSemesterPlan,
  getSemesterPlanForUser,
  listSemesterPlansForUser,
  loadPlanningContext
};
