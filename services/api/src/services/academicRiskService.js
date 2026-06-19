const { analyzeAcademicRisks } = require("../risk/academicRiskAnalyzer");
const { roundCredits } = require("../graduation/graduationProgressCalculator");
const {
  createAcademicRiskAnalysis,
  findAcademicRiskAnalysesByUserId,
  findAcademicRiskAnalysisByIdAndUserId
} = require("../models/academicRiskModel");
const { findCourseById } = require("../models/courseModel");
const { findSemesterPlanByIdAndUserId } = require("../models/semesterPlanModel");
const { loadPlanningContext } = require("./semesterPlanService");

function normalizeCourseId(courseId) {
  return String(courseId);
}

function buildPlanViewFromSemesterPlan(planDocument) {
  const primarySemester = planDocument.semesters?.[0] ?? null;

  return {
    planId: planDocument._id.toString(),
    semesterCode: primarySemester?.semesterCode ?? null,
    plannedCourses: primarySemester?.plannedCourses ?? [],
    maxCredits: primarySemester?.constraintsSnapshot?.maxCredits ?? primarySemester?.goalCredits ?? null,
    minCredits: primarySemester?.constraintsSnapshot?.minCredits ?? 0,
    explanation: planDocument.explanation ?? {},
    plannerType: planDocument.plannerType ?? null,
    analysisSource: "semester_plan"
  };
}

async function buildPlanViewFromAdhoc(database, degree, options) {
  const plannedCourses = [];

  for (const courseId of options.courseIds) {
    const catalogCourse = await findCourseById(database, courseId);
    if (!catalogCourse) {
      plannedCourses.push({
        courseId: normalizeCourseId(courseId),
        courseNumber: null,
        courseTitle: null,
        credits: 0,
        category: "adhoc",
        reason: "Ad-hoc proposed course"
      });
      continue;
    }

    if (
      catalogCourse.institutionId !== degree.institutionId ||
      catalogCourse.catalogYear !== degree.catalogYear
    ) {
      plannedCourses.push({
        courseId: normalizeCourseId(courseId),
        courseNumber: catalogCourse.number,
        courseTitle: catalogCourse.title,
        credits: roundCredits(catalogCourse.credits ?? 0),
        category: "adhoc",
        reason: "Ad-hoc proposed course outside active degree catalog scope"
      });
      continue;
    }

    plannedCourses.push({
      courseId: normalizeCourseId(catalogCourse._id),
      courseNumber: catalogCourse.number,
      courseTitle: catalogCourse.title,
      credits: roundCredits(catalogCourse.credits ?? 0),
      category: "adhoc",
      reason: "Ad-hoc proposed course"
    });
  }

  return {
    planId: null,
    semesterCode: options.semesterCode,
    plannedCourses,
    maxCredits: options.maxCredits ?? null,
    minCredits: options.minCredits ?? 0,
    explanation: {},
    plannerType: null,
    analysisSource: "adhoc_courses"
  };
}

async function analyzeAndStoreAcademicRisks(database, userId, options) {
  const context = await loadPlanningContext(database, userId);
  if (context.status !== "ok") {
    return context;
  }

  let planView;

  if (options.planId) {
    const plan = await findSemesterPlanByIdAndUserId(database, options.planId, userId);
    if (!plan) {
      return { status: "plan_not_found" };
    }

    planView = buildPlanViewFromSemesterPlan(plan);
  } else {
    planView = await buildPlanViewFromAdhoc(database, context.degree, options);
  }

  const analysisData = analyzeAcademicRisks({
    profile: context.profile,
    degree: context.degree,
    catalogCourses: context.catalogCourses,
    graduationProgress: context.graduationProgress,
    completedCourseRecords: context.completedCourseRecords,
    planView
  });

  const storedAnalysis = await createAcademicRiskAnalysis(database, userId, analysisData);

  return {
    status: "ok",
    analysis: storedAnalysis
  };
}

async function listAcademicRiskAnalysesForUser(database, userId, pagination) {
  return findAcademicRiskAnalysesByUserId(database, userId, pagination);
}

async function getAcademicRiskAnalysisForUser(database, userId, analysisId) {
  const analysis = await findAcademicRiskAnalysisByIdAndUserId(database, analysisId, userId);
  if (!analysis) {
    return { status: "not_found" };
  }

  return {
    status: "ok",
    analysis
  };
}

module.exports = {
  analyzeAndStoreAcademicRisks,
  buildPlanViewFromAdhoc,
  buildPlanViewFromSemesterPlan,
  getAcademicRiskAnalysisForUser,
  listAcademicRiskAnalysesForUser
};
