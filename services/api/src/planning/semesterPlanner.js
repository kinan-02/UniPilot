const {
  buildEffectiveCompletions,
  roundCredits
} = require("../graduation/graduationProgressCalculator");

const DEFAULT_MAX_CREDITS = 18;

function normalizeCourseId(courseId) {
  return String(courseId);
}

function getCourseCredits(course) {
  return roundCredits(course.credits ?? 0);
}

function prerequisitesMet(course, completedCourseIds) {
  const prerequisiteIds = (course.prerequisites ?? []).map((courseId) => normalizeCourseId(courseId));
  return prerequisiteIds.every((courseId) => completedCourseIds.has(courseId));
}

function buildCourseSnapshot(course, { category, reason }) {
  return {
    courseId: normalizeCourseId(course._id),
    courseNumber: course.number,
    courseTitle: course.title,
    credits: getCourseCredits(course),
    category,
    reason
  };
}

function sortCoursesByNumber(courses) {
  return [...courses].sort((left, right) => String(left.number).localeCompare(String(right.number)));
}

function resolveCatalogCourse(coursesById, courseRef) {
  const courseId = normalizeCourseId(courseRef.courseId ?? courseRef._id);
  return coursesById.get(courseId) ?? null;
}

function buildCandidatePools({
  catalogCourses,
  graduationProgress,
  requirements,
  completedCourseIds
}) {
  const coursesById = new Map(
    catalogCourses.map((course) => [normalizeCourseId(course._id), course])
  );

  const mandatoryRemainingRefs = graduationProgress.remainingMandatoryCourses ?? [];
  const mandatoryCandidates = sortCoursesByNumber(
    mandatoryRemainingRefs
      .map((courseRef) => resolveCatalogCourse(coursesById, courseRef))
      .filter(Boolean)
      .filter((course) => !completedCourseIds.has(normalizeCourseId(course._id)))
  );

  const electiveRequirementProgress = (graduationProgress.requirementProgress ?? []).find(
    (entry) => entry.requirementType === "elective"
  );
  const electiveRequirement = requirements.find(
    (requirement) => requirement.requirementType === "elective"
  );
  const electivePoolIds = new Set(
    (electiveRequirement?.courseSet ?? []).map((courseId) => normalizeCourseId(courseId))
  );

  const electiveRemainingRefs = electiveRequirementProgress?.remainingCourses ?? [];
  const electiveCandidates = sortCoursesByNumber(
    electiveRemainingRefs
      .map((courseRef) => resolveCatalogCourse(coursesById, courseRef))
      .filter(Boolean)
      .filter((course) => electivePoolIds.has(normalizeCourseId(course._id)))
      .filter((course) => !completedCourseIds.has(normalizeCourseId(course._id)))
  );

  return {
    coursesById,
    mandatoryCandidates,
    electiveCandidates
  };
}

function collectBlockedCourses(candidates, completedCourseIds) {
  return candidates
    .filter((course) => !prerequisitesMet(course, completedCourseIds))
    .map((course) => ({
      courseId: normalizeCourseId(course._id),
      courseNumber: course.number,
      courseTitle: course.title,
      missingPrerequisiteIds: (course.prerequisites ?? [])
        .map((courseId) => normalizeCourseId(courseId))
        .filter((courseId) => !completedCourseIds.has(courseId))
    }));
}

function generateDeterministicSemesterPlan({
  profile,
  degree,
  catalogCourses,
  requirements,
  graduationProgress,
  completedCourseRecords,
  semesterCode,
  maxCredits,
  minCredits,
  name
}) {
  const effectiveCompletions = buildEffectiveCompletions(completedCourseRecords);
  const completedCourseIds = new Set(effectiveCompletions.keys());

  const maxCreditsLimit = roundCredits(
    maxCredits ?? profile.preferences?.maxCreditsPerSemester ?? DEFAULT_MAX_CREDITS
  );
  const minCreditsTarget = roundCredits(minCredits ?? 0);

  const { coursesById, mandatoryCandidates, electiveCandidates } = buildCandidatePools({
    catalogCourses,
    graduationProgress,
    requirements,
    completedCourseIds
  });

  const eligibleMandatory = mandatoryCandidates.filter((course) =>
    prerequisitesMet(course, completedCourseIds)
  );
  const eligibleElectives = electiveCandidates.filter((course) =>
    prerequisitesMet(course, completedCourseIds)
  );

  const blockedMandatory = collectBlockedCourses(mandatoryCandidates, completedCourseIds);
  const blockedElectives = collectBlockedCourses(electiveCandidates, completedCourseIds);

  const selectedCourses = [];
  const skippedDueToWorkload = [];
  let totalCredits = 0;

  for (const course of eligibleMandatory) {
    const courseCredits = getCourseCredits(course);
    if (totalCredits + courseCredits <= maxCreditsLimit) {
      selectedCourses.push(
        buildCourseSnapshot(course, {
          category: "mandatory",
          reason: "Remaining mandatory degree requirement"
        })
      );
      totalCredits = roundCredits(totalCredits + courseCredits);
      continue;
    }

    skippedDueToWorkload.push({
      courseId: normalizeCourseId(course._id),
      courseNumber: course.number,
      courseTitle: course.title,
      credits: courseCredits,
      reason: "Would exceed maxCredits workload limit"
    });
  }

  const mandatorySlotsRemaining = eligibleMandatory.length - selectedCourses.length;
  const shouldIncludeElectives =
    totalCredits < maxCreditsLimit &&
    (mandatorySlotsRemaining > 0 ||
      eligibleMandatory.length === 0 ||
      totalCredits < minCreditsTarget);

  if (shouldIncludeElectives) {
    for (const course of eligibleElectives) {
      const courseCredits = getCourseCredits(course);
      if (totalCredits + courseCredits > maxCreditsLimit) {
        skippedDueToWorkload.push({
          courseId: normalizeCourseId(course._id),
          courseNumber: course.number,
          courseTitle: course.title,
          credits: courseCredits,
          reason: "Would exceed maxCredits workload limit"
        });
        continue;
      }

      selectedCourses.push(
        buildCourseSnapshot(course, {
          category: "elective",
          reason:
            totalCredits < minCreditsTarget
              ? "Elective selected to approach minCredits target"
              : "Elective selected after mandatory priorities"
        })
      );
      totalCredits = roundCredits(totalCredits + courseCredits);
    }
  }

  const meetsMinCredits = totalCredits >= minCreditsTarget || selectedCourses.length === 0;
  const partialPlan = selectedCourses.length > 0 && !meetsMinCredits;
  const emptyPlan = selectedCourses.length === 0;

  const rulesApplied = [
    "Exclude courses already completed with a passing grade",
    "Exclude failed attempts from completed-course eligibility",
    "Prioritize remaining mandatory courses before electives",
    "Recommend only courses with satisfied prerequisites",
    "Respect maxCredits workload limit",
    "Use profile preferred workload when maxCredits is not provided"
  ];

  if (minCreditsTarget > 0) {
    rulesApplied.push("Attempt to reach minCredits when capacity allows");
  }

  const explanation = {
    summary: emptyPlan
      ? "No eligible courses are available for the requested semester workload"
      : partialPlan
        ? "Partial plan generated because workload limits prevented reaching minCredits"
        : `Recommended ${selectedCourses.length} course(s) for ${semesterCode}`,
    rulesApplied,
    semesterCode,
    maxCredits: maxCreditsLimit,
    minCredits: minCreditsTarget,
    totalRecommendedCredits: totalCredits,
    selectedCount: selectedCourses.length,
    mandatoryRemainingBeforePlan: mandatoryCandidates.length,
    completedCoursesExcluded: completedCourseIds.size,
    blockedByPrerequisites: [...blockedMandatory, ...blockedElectives],
    skippedDueToWorkload,
    partialPlan,
    emptyPlan,
    meetsMinCredits
  };

  const planName =
    name ?? `Generated plan for ${semesterCode} (${degree.code}, ${new Date().toISOString().slice(0, 10)})`;

  return {
    name: planName,
    status: "draft",
    version: 1,
    plannerType: "deterministic",
    assumptions: {
      generatedBy: "deterministic-semester-planner",
      semesterCode,
      maxCredits: maxCreditsLimit,
      minCredits: minCreditsTarget,
      degreeId: normalizeCourseId(degree._id),
      catalogYear: degree.catalogYear,
      catalogVersion: degree.catalogVersion,
      graduationStatusSummary: graduationProgress.statusSummary
    },
    explanation,
    semesters: [
      {
        semesterCode,
        goalCredits: maxCreditsLimit,
        order: 1,
        plannedCourses: selectedCourses,
        notes: explanation.summary,
        constraintsSnapshot: {
          maxCredits: maxCreditsLimit,
          minCredits: minCreditsTarget,
          profileMaxCreditsPerSemester: profile.preferences?.maxCreditsPerSemester ?? null
        }
      }
    ]
  };
}

module.exports = {
  DEFAULT_MAX_CREDITS,
  generateDeterministicSemesterPlan,
  prerequisitesMet
};
