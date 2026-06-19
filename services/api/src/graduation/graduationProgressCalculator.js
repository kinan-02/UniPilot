const PASSING_GRADES = new Set([
  "A+",
  "A",
  "A-",
  "B+",
  "B",
  "B-",
  "C+",
  "C",
  "C-",
  "D",
  "Pass"
]);

function roundCredits(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function roundPercentage(value) {
  return Math.round((Number(value) + Number.EPSILON) * 100) / 100;
}

function isPassingGrade(grade) {
  return PASSING_GRADES.has(grade);
}

function normalizeCourseId(courseId) {
  return String(courseId);
}

function getRequirementCourseIds(requirement) {
  return (requirement.courseSet ?? []).map((courseId) => normalizeCourseId(courseId));
}

function buildEffectiveCompletions(completedCourseRecords) {
  const bestByCourseId = new Map();

  for (const record of completedCourseRecords) {
    if (!isPassingGrade(record.grade)) {
      continue;
    }

    const courseId = normalizeCourseId(record.courseId);
    const existing = bestByCourseId.get(courseId);
    const candidate = {
      courseId,
      creditsEarned: roundCredits(record.creditsEarned),
      grade: record.grade,
      semesterCode: record.semesterCode,
      recordedAt: record.recordedAt
    };

    if (!existing) {
      bestByCourseId.set(courseId, candidate);
      continue;
    }

    if (candidate.creditsEarned > existing.creditsEarned) {
      bestByCourseId.set(courseId, candidate);
      continue;
    }

    if (
      candidate.creditsEarned === existing.creditsEarned &&
      new Date(candidate.recordedAt) > new Date(existing.recordedAt)
    ) {
      bestByCourseId.set(courseId, candidate);
    }
  }

  return bestByCourseId;
}

function buildCourseProgressEntry(courseId, catalogCourse, completion) {
  return {
    courseId,
    courseNumber: catalogCourse?.number ?? null,
    courseTitle: catalogCourse?.title ?? null,
    catalogCredits: catalogCourse?.credits ?? null,
    creditsEarned: completion ? completion.creditsEarned : null,
    grade: completion?.grade ?? null,
    semesterCode: completion?.semesterCode ?? null
  };
}

function evaluateRequirement(requirement, effectiveCompletions, coursesById) {
  const courseIds = getRequirementCourseIds(requirement);
  const ruleType = requirement.ruleExpression?.type;
  const operator = requirement.ruleExpression?.operator;
  const minCredits = requirement.minCredits ?? 0;

  if (ruleType === "course_set" && operator === "all_of") {
    const completedCourses = [];
    const remainingCourses = [];

    for (const courseId of courseIds) {
      const completion = effectiveCompletions.get(courseId);
      const catalogCourse = coursesById.get(courseId);
      const entry = buildCourseProgressEntry(courseId, catalogCourse, completion);

      if (completion) {
        completedCourses.push(entry);
      } else {
        remainingCourses.push(entry);
      }
    }

    const creditsCompleted = roundCredits(
      completedCourses.reduce((sum, course) => sum + (course.creditsEarned ?? 0), 0)
    );
    const satisfied = remainingCourses.length === 0;

    return {
      requirementId: normalizeCourseId(requirement._id),
      title: requirement.title,
      requirementType: requirement.requirementType,
      isMandatory: Boolean(requirement.isMandatory),
      status: satisfied ? "satisfied" : creditsCompleted > 0 ? "in_progress" : "not_started",
      minCredits,
      creditsCompleted,
      creditsRemaining: satisfied ? 0 : roundCredits(Math.max(0, minCredits - creditsCompleted)),
      completedCourses,
      remainingCourses
    };
  }

  if (ruleType === "credit_pool" || ruleType === "total_credits") {
    let creditsCompleted = 0;

    if (ruleType === "total_credits") {
      creditsCompleted = roundCredits(
        [...effectiveCompletions.values()].reduce((sum, completion) => sum + completion.creditsEarned, 0)
      );
    } else {
      creditsCompleted = roundCredits(
        courseIds.reduce((sum, courseId) => {
          const completion = effectiveCompletions.get(courseId);
          return sum + (completion?.creditsEarned ?? 0);
        }, 0)
      );
    }

    const completedCourses = courseIds
      .filter((courseId) => effectiveCompletions.has(courseId))
      .map((courseId) =>
        buildCourseProgressEntry(courseId, coursesById.get(courseId), effectiveCompletions.get(courseId))
      );

    const remainingCourses = courseIds
      .filter((courseId) => !effectiveCompletions.has(courseId))
      .map((courseId) => buildCourseProgressEntry(courseId, coursesById.get(courseId), null));

    const satisfied = creditsCompleted >= minCredits;

    return {
      requirementId: normalizeCourseId(requirement._id),
      title: requirement.title,
      requirementType: requirement.requirementType,
      isMandatory: Boolean(requirement.isMandatory),
      status: satisfied ? "satisfied" : creditsCompleted > 0 ? "in_progress" : "not_started",
      minCredits,
      creditsCompleted,
      creditsRemaining: satisfied ? 0 : roundCredits(Math.max(0, minCredits - creditsCompleted)),
      completedCourses,
      remainingCourses
    };
  }

  return {
    requirementId: normalizeCourseId(requirement._id),
    title: requirement.title,
    requirementType: requirement.requirementType,
    isMandatory: Boolean(requirement.isMandatory),
    status: "unsupported",
    minCredits,
    creditsCompleted: 0,
    creditsRemaining: minCredits,
    completedCourses: [],
    remainingCourses: courseIds.map((courseId) =>
      buildCourseProgressEntry(courseId, coursesById.get(courseId), null)
    )
  };
}

function dedupeCoursesById(courseEntries) {
  const byId = new Map();

  for (const entry of courseEntries) {
    if (!byId.has(entry.courseId)) {
      byId.set(entry.courseId, entry);
    }
  }

  return [...byId.values()];
}

function buildStatusSummary({ completedCredits, missingRequirements }) {
  if (completedCredits <= 0) {
    return "not_started";
  }

  if (missingRequirements.length === 0) {
    return "complete";
  }

  const mandatoryMissing = missingRequirements.some((requirement) => requirement.isMandatory);
  if (!mandatoryMissing) {
    return "mandatory_requirements_met";
  }

  return "in_progress";
}

function calculateGraduationProgress({ degree, requirements, catalogCourses, completedCourseRecords }) {
  const coursesById = new Map(
    catalogCourses.map((course) => [normalizeCourseId(course._id), course])
  );
  const effectiveCompletions = buildEffectiveCompletions(completedCourseRecords);
  const sortedRequirements = [...requirements].sort(
    (left, right) => (left.priority ?? 0) - (right.priority ?? 0)
  );

  const requirementProgress = sortedRequirements.map((requirement) =>
    evaluateRequirement(requirement, effectiveCompletions, coursesById)
  );

  const totalCreditsRequirement = sortedRequirements.find(
    (requirement) => requirement.ruleExpression?.type === "total_credits"
  );
  const totalRequiredCredits =
    totalCreditsRequirement?.minCredits ?? degree.metadata?.totalCredits ?? 0;

  const completedCredits = roundCredits(
    [...effectiveCompletions.values()].reduce((sum, completion) => sum + completion.creditsEarned, 0)
  );
  const creditsRemaining = roundCredits(Math.max(0, totalRequiredCredits - completedCredits));
  const completionPercentage =
    totalRequiredCredits > 0
      ? roundPercentage(Math.min(100, (completedCredits / totalRequiredCredits) * 100))
      : 0;

  const mandatoryRequirementProgress = requirementProgress.filter((entry) => entry.isMandatory);
  const electiveRequirementProgress = requirementProgress.filter((entry) => !entry.isMandatory);

  const completedMandatoryCourses = dedupeCoursesById(
    mandatoryRequirementProgress.flatMap((entry) => entry.completedCourses)
  );
  const remainingMandatoryCourses = dedupeCoursesById(
    mandatoryRequirementProgress.flatMap((entry) => entry.remainingCourses)
  ).filter(
    (course) => !completedMandatoryCourses.some((completed) => completed.courseId === course.courseId)
  );

  const electiveCreditsRequired = roundCredits(
    electiveRequirementProgress.reduce((sum, entry) => sum + (entry.minCredits ?? 0), 0)
  );
  const completedElectiveCredits = roundCredits(
    electiveRequirementProgress.reduce((sum, entry) => sum + entry.creditsCompleted, 0)
  );
  const remainingElectiveCredits = roundCredits(
    Math.max(0, electiveCreditsRequired - completedElectiveCredits)
  );

  const missingRequirements = requirementProgress
    .filter((entry) => entry.status !== "satisfied")
    .map((entry) => ({
      requirementId: entry.requirementId,
      title: entry.title,
      requirementType: entry.requirementType,
      isMandatory: entry.isMandatory,
      status: entry.status,
      creditsCompleted: entry.creditsCompleted,
      creditsRequired: entry.minCredits,
      creditsRemaining: entry.creditsRemaining,
      remainingCourseCount: entry.remainingCourses.length
    }));

  const statusSummary = buildStatusSummary({ completedCredits, missingRequirements });

  return {
    degreeId: normalizeCourseId(degree._id),
    degreeCode: degree.code,
    degreeName: degree.name,
    catalogYear: degree.catalogYear,
    catalogVersion: degree.catalogVersion,
    completedCredits,
    totalRequiredCredits,
    creditsRemaining,
    completionPercentage,
    completedMandatoryCourses,
    remainingMandatoryCourses,
    completedElectiveCredits,
    remainingElectiveCredits,
    requirementProgress,
    missingRequirements,
    statusSummary
  };
}

module.exports = {
  PASSING_GRADES,
  buildEffectiveCompletions,
  calculateGraduationProgress,
  evaluateRequirement,
  isPassingGrade,
  roundCredits
};
