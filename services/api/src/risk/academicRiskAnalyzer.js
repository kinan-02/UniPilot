const {
  buildEffectiveCompletions,
  isPassingGrade,
  roundCredits
} = require("../graduation/graduationProgressCalculator");

const SEVERITY_RANK = {
  low: 1,
  medium: 2,
  high: 3
};

const ADVANCED_LEVELS = new Set(["graduate", "advanced", "doctoral"]);
const ADVANCED_TAGS = new Set(["advanced", "graduate", "capstone"]);

function normalizeCourseId(courseId) {
  return String(courseId);
}

function getCourseCredits(course) {
  return roundCredits(course?.credits ?? 0);
}

function buildRisk({
  riskType,
  severity,
  title,
  explanation,
  evidence,
  suggestedFixes,
  relatedCourseIds = []
}) {
  return {
    riskType,
    severity,
    title,
    explanation,
    evidence,
    suggestedFixes,
    source: "rule",
    relatedCourseIds
  };
}

function buildFailedCourseAttempts(completedCourseRecords) {
  const failedByCourseId = new Map();

  for (const record of completedCourseRecords) {
    if (isPassingGrade(record.grade)) {
      continue;
    }

    const courseId = normalizeCourseId(record.courseId);
    const existing = failedByCourseId.get(courseId);
    const candidate = {
      courseId,
      grade: record.grade,
      semesterCode: record.semesterCode,
      attempt: record.attempt ?? 1
    };

    if (!existing || candidate.attempt > existing.attempt) {
      failedByCourseId.set(courseId, candidate);
    }
  }

  const effectiveCompletions = buildEffectiveCompletions(completedCourseRecords);
  for (const courseId of effectiveCompletions.keys()) {
    failedByCourseId.delete(courseId);
  }

  return failedByCourseId;
}

function isAdvancedCourse(course) {
  if (!course) {
    return false;
  }

  if (course.level && ADVANCED_LEVELS.has(String(course.level).toLowerCase())) {
    return true;
  }

  return (course.tags ?? []).some((tag) => ADVANCED_TAGS.has(String(tag).toLowerCase()));
}

function prerequisitesMetForCourse(course, satisfiedCourseIds) {
  const prerequisiteIds = (course.prerequisites ?? []).map((courseId) => normalizeCourseId(courseId));
  return prerequisiteIds.every((courseId) => satisfiedCourseIds.has(courseId));
}

function summarizeRisks(risks) {
  const counts = { low: 0, medium: 0, high: 0 };

  for (const risk of risks) {
    counts[risk.severity] += 1;
  }

  let highestSeverity = null;
  for (const severity of ["high", "medium", "low"]) {
    if (counts[severity] > 0) {
      highestSeverity = severity;
      break;
    }
  }

  return {
    totalRisks: risks.length,
    highestSeverity,
    counts
  };
}

function analyzeAcademicRisks({
  profile,
  degree,
  catalogCourses,
  graduationProgress,
  completedCourseRecords,
  planView
}) {
  const coursesById = new Map(
    catalogCourses.map((course) => [normalizeCourseId(course._id), course])
  );
  const effectiveCompletions = buildEffectiveCompletions(completedCourseRecords);
  const completedCourseIds = new Set(effectiveCompletions.keys());
  const failedAttempts = buildFailedCourseAttempts(completedCourseRecords);
  const risks = [];

  const plannedCourses = planView.plannedCourses ?? [];
  const plannedCourseIds = plannedCourses.map((course) => normalizeCourseId(course.courseId));
  const uniquePlannedCourseIds = new Set(plannedCourseIds);
  const maxCreditsLimit = roundCredits(
    planView.maxCredits ?? profile.preferences?.maxCreditsPerSemester ?? 18
  );
  const minCreditsTarget = roundCredits(planView.minCredits ?? 0);
  const totalPlannedCredits = roundCredits(
    plannedCourses.reduce((sum, course) => sum + roundCredits(course.credits ?? 0), 0)
  );

  const remainingMandatoryIds = new Set(
    (graduationProgress.remainingMandatoryCourses ?? []).map((course) => normalizeCourseId(course.courseId))
  );

  if (plannedCourses.length === 0) {
    risks.push(
      buildRisk({
        riskType: "empty_plan",
        severity: "high",
        title: "Empty semester plan",
        explanation: "The plan does not include any courses for the target semester.",
        evidence: {
          semesterCode: planView.semesterCode,
          totalPlannedCredits: 0
        },
        suggestedFixes: [
          "Add remaining mandatory courses that satisfy prerequisites",
          "Increase maxCredits if workload limits blocked course selection"
        ]
      })
    );
  }

  if (planView.explanation?.partialPlan) {
    risks.push(
      buildRisk({
        riskType: "partial_plan",
        severity: minCreditsTarget > 0 && totalPlannedCredits < minCreditsTarget ? "medium" : "low",
        title: "Partial semester plan",
        explanation: planView.explanation.summary ?? "The plan could not fully satisfy workload targets.",
        evidence: {
          partialPlan: true,
          totalPlannedCredits,
          maxCredits: maxCreditsLimit,
          minCredits: minCreditsTarget,
          blockedByPrerequisites: planView.explanation.blockedByPrerequisites?.length ?? 0,
          skippedDueToWorkload: planView.explanation.skippedDueToWorkload?.length ?? 0
        },
        suggestedFixes: [
          "Review blocked prerequisites and complete or schedule prerequisite courses first",
          "Adjust maxCredits or spread courses across future semesters"
        ]
      })
    );
  }

  if (totalPlannedCredits > maxCreditsLimit) {
    risks.push(
      buildRisk({
        riskType: "credit_overload",
        severity: "high",
        title: "Credit overload",
        explanation: `The plan schedules ${totalPlannedCredits} credits, which exceeds the workload limit of ${maxCreditsLimit}.`,
        evidence: {
          totalPlannedCredits,
          maxCredits: maxCreditsLimit,
          excessCredits: roundCredits(totalPlannedCredits - maxCreditsLimit)
        },
        suggestedFixes: [
          `Reduce planned courses to ${maxCreditsLimit} credits or fewer`,
          "Move lower-priority courses to a later semester"
        ],
        relatedCourseIds: plannedCourseIds
      })
    );
  }

  if (minCreditsTarget > 0 && totalPlannedCredits < minCreditsTarget && plannedCourses.length > 0) {
    risks.push(
      buildRisk({
        riskType: "too_few_credits",
        severity: "medium",
        title: "Too few credits planned",
        explanation: `The plan schedules ${totalPlannedCredits} credits, below the minimum target of ${minCreditsTarget}.`,
        evidence: {
          totalPlannedCredits,
          minCredits: minCreditsTarget,
          shortfallCredits: roundCredits(minCreditsTarget - totalPlannedCredits)
        },
        suggestedFixes: [
          "Add eligible mandatory or elective courses that satisfy prerequisites",
          "Lower minCredits only if your degree policy allows a lighter semester"
        ]
      })
    );
  }

  const profileMaxCredits = profile.preferences?.maxCreditsPerSemester;
  if (
    profileMaxCredits !== undefined &&
    profileMaxCredits !== null &&
    totalPlannedCredits > roundCredits(profileMaxCredits) &&
    totalPlannedCredits <= maxCreditsLimit
  ) {
    risks.push(
      buildRisk({
        riskType: "credit_overload",
        severity: "medium",
        title: "Exceeds preferred semester workload",
        explanation: `The plan schedules ${totalPlannedCredits} credits, above your profile preference of ${profileMaxCredits} credits per semester.`,
        evidence: {
          totalPlannedCredits,
          profileMaxCreditsPerSemester: profileMaxCredits
        },
        suggestedFixes: [
          "Align the plan with your preferred maxCreditsPerSemester setting",
          "Update profile preferences if this workload is intentional"
        ],
        relatedCourseIds: plannedCourseIds
      })
    );
  }

  if (plannedCourseIds.length !== uniquePlannedCourseIds.size) {
    const duplicateIds = plannedCourseIds.filter(
      (courseId, index) => plannedCourseIds.indexOf(courseId) !== index
    );

    risks.push(
      buildRisk({
        riskType: "duplicate_planned_course",
        severity: "medium",
        title: "Duplicate courses in plan",
        explanation: "The same course appears more than once in the planned semester.",
        evidence: {
          duplicateCourseIds: [...new Set(duplicateIds)]
        },
        suggestedFixes: ["Remove duplicate course entries from the semester plan"],
        relatedCourseIds: [...new Set(duplicateIds)]
      })
    );
  }

  const satisfiedPrerequisiteIds = new Set(completedCourseIds);
  const unknownCourseIds = [];

  for (const plannedCourse of plannedCourses) {
    const courseId = normalizeCourseId(plannedCourse.courseId);
    const catalogCourse = coursesById.get(courseId);

    if (!catalogCourse) {
      unknownCourseIds.push(courseId);
      continue;
    }

    if (completedCourseIds.has(courseId)) {
      risks.push(
        buildRisk({
          riskType: "course_already_completed",
          severity: "high",
          title: "Course already completed",
          explanation: `${catalogCourse.title} (${catalogCourse.number}) is already completed with a passing grade.`,
          evidence: {
            courseId,
            courseNumber: catalogCourse.number,
            completedGrade: effectiveCompletions.get(courseId)?.grade ?? null
          },
          suggestedFixes: ["Remove the completed course from the semester plan"],
          relatedCourseIds: [courseId]
        })
      );
    }

    if (failedAttempts.has(courseId)) {
      const failedAttempt = failedAttempts.get(courseId);
      risks.push(
        buildRisk({
          riskType: "failed_course_retake",
          severity: "medium",
          title: "Retaking a previously failed course",
          explanation: `${catalogCourse.title} (${catalogCourse.number}) has a prior failing attempt and is scheduled again.`,
          evidence: {
            courseId,
            courseNumber: catalogCourse.number,
            priorGrade: failedAttempt.grade,
            priorSemesterCode: failedAttempt.semesterCode,
            attempt: failedAttempt.attempt
          },
          suggestedFixes: [
            "Confirm prerequisite preparation before retaking the course",
            "Consider academic support resources for this course"
          ],
          relatedCourseIds: [courseId]
        })
      );
    }

    if (!prerequisitesMetForCourse(catalogCourse, satisfiedPrerequisiteIds)) {
      const missingPrerequisiteIds = (catalogCourse.prerequisites ?? [])
        .map((courseId) => normalizeCourseId(courseId))
        .filter((courseId) => !satisfiedPrerequisiteIds.has(courseId));

      risks.push(
        buildRisk({
          riskType: "unmet_prerequisites",
          severity: "high",
          title: "Unmet prerequisites",
          explanation: `${catalogCourse.title} (${catalogCourse.number}) is scheduled before its prerequisites are satisfied.`,
          evidence: {
            courseId,
            courseNumber: catalogCourse.number,
            missingPrerequisiteIds,
            missingPrerequisites: missingPrerequisiteIds.map((prerequisiteId) => {
              const prerequisiteCourse = coursesById.get(prerequisiteId);
              return {
                courseId: prerequisiteId,
                courseNumber: prerequisiteCourse?.number ?? null,
                courseTitle: prerequisiteCourse?.title ?? null
              };
            })
          },
          suggestedFixes: [
            "Complete or schedule prerequisite courses before this course",
            "Reorder the plan so prerequisites appear earlier in the semester"
          ],
          relatedCourseIds: [courseId, ...missingPrerequisiteIds]
        })
      );
    }

    satisfiedPrerequisiteIds.add(courseId);
  }

  if (unknownCourseIds.length > 0) {
    risks.push(
      buildRisk({
        riskType: "unknown_catalog_course",
        severity: "high",
        title: "Unknown catalog courses in plan",
        explanation: "One or more planned courses are not present in the published degree catalog.",
        evidence: {
          unknownCourseIds
        },
        suggestedFixes: ["Replace unknown course ids with valid catalog courses for your degree"],
        relatedCourseIds: unknownCourseIds
      })
    );
  }

  const plannedMandatoryCount = plannedCourses.filter((course) => {
    const courseId = normalizeCourseId(course.courseId);
    return remainingMandatoryIds.has(courseId);
  }).length;

  const plannedElectiveOnly =
    plannedCourses.length > 0 &&
    plannedMandatoryCount === 0 &&
    (graduationProgress.remainingMandatoryCourses ?? []).length > 0;

  if (plannedElectiveOnly) {
    risks.push(
      buildRisk({
        riskType: "no_mandatory_progress",
        severity: "medium",
        title: "No mandatory degree progress in plan",
        explanation:
          "The plan includes only electives or non-mandatory courses while mandatory degree requirements remain outstanding.",
        evidence: {
          remainingMandatoryCourseCount: graduationProgress.remainingMandatoryCourses.length,
          plannedCourseCount: plannedCourses.length
        },
        suggestedFixes: [
          "Add remaining mandatory courses that satisfy prerequisites",
          "Use the semester planner to prioritize mandatory requirements"
        ],
        relatedCourseIds: plannedCourseIds
      })
    );
  }

  if (
    plannedCourses.length > 0 &&
    plannedMandatoryCount === 0 &&
    (graduationProgress.remainingMandatoryCourses ?? []).length > 0 &&
    !plannedElectiveOnly
  ) {
    risks.push(
      buildRisk({
        riskType: "insufficient_graduation_progress",
        severity: "low",
        title: "Limited graduation progress in plan",
        explanation:
          "The planned courses do not include any remaining mandatory degree requirements.",
        evidence: {
          remainingMandatoryCourseCount: graduationProgress.remainingMandatoryCourses.length,
          plannedMandatoryCount
        },
        suggestedFixes: [
          "Include at least one remaining mandatory course if prerequisites allow"
        ],
        relatedCourseIds: plannedCourseIds
      })
    );
  }

  const advancedCourses = plannedCourses
    .map((plannedCourse) => coursesById.get(normalizeCourseId(plannedCourse.courseId)))
    .filter((course) => isAdvancedCourse(course));

  if (advancedCourses.length >= 3) {
    risks.push(
      buildRisk({
        riskType: "too_many_advanced_courses",
        severity: "medium",
        title: "Heavy advanced course load",
        explanation: `The plan includes ${advancedCourses.length} advanced-level courses in one semester.`,
        evidence: {
          advancedCourseCount: advancedCourses.length,
          advancedCourses: advancedCourses.map((course) => ({
            courseId: normalizeCourseId(course._id),
            courseNumber: course.number,
            courseTitle: course.title,
            level: course.level ?? null
          }))
        },
        suggestedFixes: [
          "Spread advanced courses across multiple semesters",
          "Balance the schedule with lighter foundational courses"
        ],
        relatedCourseIds: advancedCourses.map((course) => normalizeCourseId(course._id))
      })
    );
  }

  const summary = summarizeRisks(risks);

  return {
    analyzerType: "deterministic",
    semesterCode: planView.semesterCode,
    planId: planView.planId ?? null,
    analysisSource: planView.analysisSource ?? "semester_plan",
    status: "open",
    summary,
    risks,
    contextSnapshot: {
      degreeId: normalizeCourseId(degree._id),
      degreeCode: degree.code,
      catalogYear: degree.catalogYear,
      planPlannerType: planView.plannerType ?? null,
      totalPlannedCredits,
      maxCredits: maxCreditsLimit,
      minCredits: minCreditsTarget,
      remainingMandatoryCourseCount: graduationProgress.remainingMandatoryCourses?.length ?? 0,
      graduationStatusSummary: graduationProgress.statusSummary
    }
  };
}

module.exports = {
  ADVANCED_LEVELS,
  analyzeAcademicRisks,
  buildFailedCourseAttempts,
  isAdvancedCourse,
  summarizeRisks
};
