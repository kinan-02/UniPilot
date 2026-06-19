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

function prerequisitesMet(course, satisfiedCourseIds) {
  const prerequisiteIds = (course.prerequisites ?? []).map((courseId) => normalizeCourseId(courseId));
  return prerequisiteIds.every((courseId) => satisfiedCourseIds.has(courseId));
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

function describeMissingPrerequisites(course, satisfiedCourseIds, coursesById) {
  const missingPrerequisiteIds = (course.prerequisites ?? [])
    .map((courseId) => normalizeCourseId(courseId))
    .filter((courseId) => !satisfiedCourseIds.has(courseId));

  const missingPrerequisites = missingPrerequisiteIds.map((courseId) => {
    const prerequisiteCourse = coursesById.get(courseId);
    return {
      courseId,
      courseNumber: prerequisiteCourse?.number ?? null,
      courseTitle: prerequisiteCourse?.title ?? null
    };
  });

  const labels = missingPrerequisites
    .map((entry) => entry.courseNumber ?? entry.courseId)
    .filter(Boolean);

  return {
    missingPrerequisiteIds,
    missingPrerequisites,
    reason:
      labels.length > 0
        ? `Blocked until prerequisite course(s) are completed or scheduled earlier: ${labels.join(", ")}`
        : "Blocked by unsatisfied prerequisites"
  };
}

function collectBlockedCourses(candidates, satisfiedCourseIds, coursesById, { category }) {
  return candidates
    .filter((course) => !prerequisitesMet(course, satisfiedCourseIds))
    .map((course) => {
      const prerequisiteDetails = describeMissingPrerequisites(course, satisfiedCourseIds, coursesById);

      return {
        courseId: normalizeCourseId(course._id),
        courseNumber: course.number,
        courseTitle: course.title,
        category,
        ...prerequisiteDetails
      };
    });
}

function buildWorkloadSkip(course, courseCredits) {
  return {
    courseId: normalizeCourseId(course._id),
    courseNumber: course.number,
    courseTitle: course.title,
    credits: courseCredits,
    reason: "Would exceed maxCredits workload limit"
  };
}

function selectCoursesFromCandidates({
  candidates,
  satisfiedCourseIds,
  maxCreditsLimit,
  startingCredits,
  category,
  defaultReason
}) {
  const selectedCourses = [];
  const skippedDueToWorkload = [];
  const remaining = [...candidates];
  let totalCredits = startingCredits;

  let progressed = true;
  while (progressed && remaining.length > 0 && totalCredits < maxCreditsLimit) {
    progressed = false;

    for (let index = 0; index < remaining.length; index += 1) {
      const course = remaining[index];
      if (!prerequisitesMet(course, satisfiedCourseIds)) {
        continue;
      }

      const courseCredits = getCourseCredits(course);
      if (totalCredits + courseCredits > maxCreditsLimit) {
        skippedDueToWorkload.push(buildWorkloadSkip(course, courseCredits));
        remaining.splice(index, 1);
        index -= 1;
        continue;
      }

      selectedCourses.push(
        buildCourseSnapshot(course, {
          category,
          reason: defaultReason
        })
      );
      satisfiedCourseIds.add(normalizeCourseId(course._id));
      totalCredits = roundCredits(totalCredits + courseCredits);
      remaining.splice(index, 1);
      index -= 1;
      progressed = true;
    }
  }

  return {
    selectedCourses,
    skippedDueToWorkload,
    remaining,
    totalCredits
  };
}

function canAddAnotherCourse(candidates, satisfiedCourseIds, remainingCredits, selectedCourseIds) {
  return candidates.some((course) => {
    const courseId = normalizeCourseId(course._id);
    if (selectedCourseIds.has(courseId)) {
      return false;
    }

    return (
      prerequisitesMet(course, satisfiedCourseIds) &&
      getCourseCredits(course) <= remainingCredits
    );
  });
}

function buildPlanSummary({
  emptyPlan,
  partialPlan,
  semesterCode,
  selectedCount,
  minCreditsTarget,
  totalCredits,
  maxCreditsLimit,
  blockedCount,
  skippedWorkloadCount
}) {
  if (emptyPlan) {
    if (blockedCount > 0) {
      return "No eligible courses are available because remaining courses are blocked by unsatisfied prerequisites";
    }

    return "No eligible courses are available for the requested semester workload";
  }

  if (partialPlan) {
    if (minCreditsTarget > 0 && totalCredits < minCreditsTarget) {
      return `Partial plan generated because workload limits prevented reaching minCredits (${totalCredits}/${minCreditsTarget})`;
    }

    if (totalCredits < maxCreditsLimit) {
      if (skippedWorkloadCount > 0 || blockedCount > 0) {
        return `Partial plan generated because only ${selectedCount} course(s) fit within maxCredits (${totalCredits}/${maxCreditsLimit})`;
      }

      return `Partial plan generated because no additional eligible courses were available below maxCredits (${totalCredits}/${maxCreditsLimit})`;
    }
  }

  return `Recommended ${selectedCount} course(s) for ${semesterCode}`;
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
  const satisfiedCourseIds = new Set(completedCourseIds);

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

  const mandatorySelection = selectCoursesFromCandidates({
    candidates: mandatoryCandidates,
    satisfiedCourseIds,
    maxCreditsLimit,
    startingCredits: 0,
    category: "mandatory",
    defaultReason: "Remaining mandatory degree requirement"
  });

  const selectedCourses = [...mandatorySelection.selectedCourses];
  const skippedDueToWorkload = [...mandatorySelection.skippedDueToWorkload];
  let totalCredits = mandatorySelection.totalCredits;

  const selectedCourseIds = new Set(selectedCourses.map((course) => course.courseId));
  const remainingMandatoryCredits = roundCredits(maxCreditsLimit - totalCredits);
  const canAddMandatory = canAddAnotherCourse(
    mandatoryCandidates,
    satisfiedCourseIds,
    remainingMandatoryCredits,
    selectedCourseIds
  );

  const shouldIncludeElectives =
    totalCredits < maxCreditsLimit &&
    electiveCandidates.length > 0 &&
    (!canAddMandatory || totalCredits < minCreditsTarget);

  if (shouldIncludeElectives) {
    const electiveSelection = selectCoursesFromCandidates({
      candidates: electiveCandidates,
      satisfiedCourseIds,
      maxCreditsLimit,
      startingCredits: totalCredits,
      category: "elective",
      defaultReason:
        totalCredits < minCreditsTarget
          ? "Elective selected to approach minCredits target"
          : "Elective selected after mandatory priorities"
    });

    selectedCourses.push(...electiveSelection.selectedCourses);
    skippedDueToWorkload.push(...electiveSelection.skippedDueToWorkload);
    totalCredits = electiveSelection.totalCredits;
  }

  const finalSelectedIds = new Set(selectedCourses.map((course) => course.courseId));
  const unselectedMandatory = mandatoryCandidates.filter(
    (course) => !finalSelectedIds.has(normalizeCourseId(course._id))
  );
  const unselectedElectives = electiveCandidates.filter(
    (course) => !finalSelectedIds.has(normalizeCourseId(course._id))
  );

  const blockedMandatory = collectBlockedCourses(unselectedMandatory, satisfiedCourseIds, coursesById, {
    category: "mandatory"
  });
  const blockedElectives = collectBlockedCourses(unselectedElectives, satisfiedCourseIds, coursesById, {
    category: "elective"
  });
  const blockedByPrerequisites = [...blockedMandatory, ...blockedElectives];

  const meetsMinCredits = totalCredits >= minCreditsTarget || selectedCourses.length === 0;
  const emptyPlan = selectedCourses.length === 0;
  const partialPlan =
    selectedCourses.length > 0 &&
    ((minCreditsTarget > 0 && totalCredits < minCreditsTarget) || totalCredits < maxCreditsLimit);

  const rulesApplied = [
    "Exclude courses already completed with a passing grade",
    "Exclude failed attempts from completed-course eligibility",
    "Prioritize remaining mandatory courses before electives",
    "Recommend only courses with satisfied prerequisites (completed or scheduled earlier in the same plan)",
    "Respect maxCredits workload limit",
    "Use profile preferred workload when maxCredits is not provided"
  ];

  if (minCreditsTarget > 0) {
    rulesApplied.push("Attempt to reach minCredits when capacity allows");
  }

  const explanation = {
    summary: buildPlanSummary({
      emptyPlan,
      partialPlan,
      semesterCode,
      selectedCount: selectedCourses.length,
      minCreditsTarget,
      totalCredits,
      maxCreditsLimit,
      blockedCount: blockedByPrerequisites.length,
      skippedWorkloadCount: skippedDueToWorkload.length
    }),
    rulesApplied,
    semesterCode,
    maxCredits: maxCreditsLimit,
    minCredits: minCreditsTarget,
    profileMaxCreditsPerSemester: profile.preferences?.maxCreditsPerSemester ?? null,
    totalRecommendedCredits: totalCredits,
    selectedCount: selectedCourses.length,
    mandatoryRemainingBeforePlan: mandatoryCandidates.length,
    completedCoursesExcluded: completedCourseIds.size,
    blockedByPrerequisites,
    skippedDueToWorkload,
    partialPlan,
    emptyPlan,
    meetsMinCredits,
    meetsMaxCredits: totalCredits >= maxCreditsLimit || selectedCourses.length === 0
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
