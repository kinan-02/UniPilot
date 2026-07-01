"""Deterministic academic risk analyzer (Phase 17)."""

from __future__ import annotations

from typing import Any

from app.services.graduation_progress_calculator import (
    build_effective_completions,
    is_passing_grade,
    pick_latest_records_by_course_id,
    round_credits,
)

ADVANCED_LEVELS = frozenset({"graduate", "advanced", "doctoral"})
ADVANCED_TAGS = frozenset({"advanced", "graduate", "capstone"})


def normalize_course_id(course_id: Any) -> str:
    return str(course_id)


def course_number(course: dict[str, Any] | None) -> str | None:
    if not course:
        return None
    value = course.get("courseNumber") or course.get("number")
    return str(value) if value is not None else None


def course_title(course: dict[str, Any] | None) -> str | None:
    if not course:
        return None
    value = course.get("title") or course.get("titleHebrew")
    return str(value) if value is not None else None


def degree_code(degree: dict[str, Any]) -> str | None:
    value = degree.get("programCode") or degree.get("code")
    return str(value) if value is not None else None


def build_risk(
    *,
    risk_type: str,
    severity: str,
    title: str,
    explanation: str,
    evidence: dict[str, Any],
    suggested_fixes: list[str],
    related_course_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "riskType": risk_type,
        "severity": severity,
        "title": title,
        "explanation": explanation,
        "evidence": evidence,
        "suggestedFixes": suggested_fixes,
        "source": "rule",
        "relatedCourseIds": related_course_ids or [],
    }


def build_failed_course_attempts(
    completed_course_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest_by_course_id = pick_latest_records_by_course_id(completed_course_records)
    effective_completions = build_effective_completions(completed_course_records)

    failed_by_course_id: dict[str, dict[str, Any]] = {}
    for course_id, record in latest_by_course_id.items():
        if course_id in effective_completions:
            continue
        if is_passing_grade(record):
            continue

        failed_by_course_id[course_id] = {
            "courseId": course_id,
            "grade": record.get("grade"),
            "semesterCode": record.get("semesterCode"),
            "attempt": record.get("attempt") or 1,
        }

    return failed_by_course_id


def is_advanced_course(course: dict[str, Any] | None) -> bool:
    if not course:
        return False

    level = course.get("level")
    if level and str(level).lower() in ADVANCED_LEVELS:
        return True

    tags = course.get("tags") or []
    return any(str(tag).lower() in ADVANCED_TAGS for tag in tags)


def prerequisites_met_for_course(
    course: dict[str, Any],
    satisfied_course_ids: set[str],
) -> bool:
    prerequisite_ids = [
        normalize_course_id(course_id) for course_id in (course.get("prerequisites") or [])
    ]
    return all(course_id in satisfied_course_ids for course_id in prerequisite_ids)


def summarize_risks(risks: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {"low": 0, "medium": 0, "high": 0}
    for risk in risks:
        counts[risk["severity"]] += 1

    highest_severity = None
    for severity in ("high", "medium", "low"):
        if counts[severity] > 0:
            highest_severity = severity
            break

    return {
        "totalRisks": len(risks),
        "highestSeverity": highest_severity,
        "counts": counts,
    }


def build_elective_pool_ids(
    pool_documents: list[dict[str, Any]],
    catalog_courses: list[dict[str, Any]],
) -> set[str]:
    pool_ids: set[str] = set()
    allowed_prefixes: list[str] = []

    courses_by_number: dict[str, dict[str, Any]] = {}
    for course in catalog_courses:
        number = course_number(course)
        if number:
            courses_by_number[number] = course

    for pool_document in pool_documents or []:
        for reference in pool_document.get("courseReferences") or []:
            number = reference.get("courseNumber")
            if number is None:
                continue
            catalog_course = courses_by_number.get(str(number))
            if catalog_course:
                pool_ids.add(normalize_course_id(catalog_course["_id"]))

        rule = pool_document.get("ruleExpression") or {}
        allowed_prefixes.extend(str(prefix) for prefix in (rule.get("allowedPrefixes") or []))

    if allowed_prefixes:
        for course in catalog_courses:
            number = course_number(course)
            if number and any(str(number).startswith(prefix) for prefix in allowed_prefixes):
                pool_ids.add(normalize_course_id(course["_id"]))

    return pool_ids


def analyze_academic_risks(
    *,
    profile: dict[str, Any],
    degree: dict[str, Any],
    catalog_courses: list[dict[str, Any]],
    pool_documents: list[dict[str, Any]],
    graduation_progress: dict[str, Any],
    completed_course_records: list[dict[str, Any]],
    plan_view: dict[str, Any],
) -> dict[str, Any]:
    courses_by_id = {
        normalize_course_id(course["_id"]): course for course in catalog_courses
    }
    effective_completions = build_effective_completions(completed_course_records)
    completed_course_ids = set(effective_completions.keys())
    failed_attempts = build_failed_course_attempts(completed_course_records)
    risks: list[dict[str, Any]] = []

    planned_courses = plan_view.get("plannedCourses") or []
    planned_course_ids = [
        normalize_course_id(course["courseId"]) for course in planned_courses
    ]
    unique_planned_course_ids = set(planned_course_ids)
    preferences = profile.get("preferences") or {}
    max_credits_limit = round_credits(
        plan_view.get("maxCredits")
        or preferences.get("maxCreditsPerSemester")
        or 18
    )
    min_credits_target = round_credits(plan_view.get("minCredits") or 0)
    total_planned_credits = round_credits(
        sum(round_credits(course.get("credits") or 0) for course in planned_courses)
    )

    remaining_mandatory_ids = {
        normalize_course_id(course["courseId"])
        for course in (graduation_progress.get("remainingMandatoryCourses") or [])
    }
    elective_pool_ids = build_elective_pool_ids(pool_documents, catalog_courses)
    explanation = plan_view.get("explanation") or {}

    if not planned_courses:
        risks.append(
            build_risk(
                risk_type="empty_plan",
                severity="high",
                title="Empty semester plan",
                explanation="The plan does not include any courses for the target semester.",
                evidence={
                    "semesterCode": plan_view.get("semesterCode"),
                    "totalPlannedCredits": 0,
                },
                suggested_fixes=[
                    "Add remaining mandatory courses that satisfy prerequisites",
                    "Increase maxCredits if workload limits blocked course selection",
                ],
            )
        )

    if explanation.get("partialPlan"):
        severity = (
            "medium"
            if min_credits_target > 0 and total_planned_credits < min_credits_target
            else "low"
        )
        risks.append(
            build_risk(
                risk_type="partial_plan",
                severity=severity,
                title="Partial semester plan",
                explanation=explanation.get("summary")
                or "The plan could not fully satisfy workload targets.",
                evidence={
                    "partialPlan": True,
                    "totalPlannedCredits": total_planned_credits,
                    "maxCredits": max_credits_limit,
                    "minCredits": min_credits_target,
                    "blockedByPrerequisites": len(explanation.get("blockedByPrerequisites") or []),
                    "skippedDueToWorkload": len(explanation.get("skippedDueToWorkload") or []),
                },
                suggested_fixes=[
                    "Review blocked prerequisites and complete or schedule prerequisite courses first",
                    "Adjust maxCredits or spread courses across future semesters",
                ],
            )
        )

    blocked_by_prerequisites = explanation.get("blockedByPrerequisites") or []
    skipped_due_to_workload = explanation.get("skippedDueToWorkload") or []

    if not explanation.get("partialPlan") and blocked_by_prerequisites:
        risks.append(
            build_risk(
                risk_type="deferred_prerequisite_blocked_courses",
                severity="low",
                title="Eligible courses deferred by prerequisites",
                explanation=(
                    "The planner left one or more courses out of this semester because "
                    "prerequisites are not yet satisfied."
                ),
                evidence={
                    "deferredCourseCount": len(blocked_by_prerequisites),
                    "deferredCourses": blocked_by_prerequisites[:10],
                },
                suggested_fixes=[
                    "Complete or schedule prerequisite courses in an earlier semester",
                    "Regenerate the plan after updating completed courses",
                ],
                related_course_ids=[
                    entry["courseId"]
                    for entry in blocked_by_prerequisites
                    if entry.get("courseId")
                ],
            )
        )

    if not explanation.get("partialPlan") and skipped_due_to_workload:
        risks.append(
            build_risk(
                risk_type="deferred_workload_limited_courses",
                severity="low",
                title="Eligible courses deferred by workload limits",
                explanation=(
                    "The planner excluded one or more eligible courses because they would "
                    "exceed the semester workload limit."
                ),
                evidence={
                    "deferredCourseCount": len(skipped_due_to_workload),
                    "deferredCourses": skipped_due_to_workload[:10],
                    "maxCredits": max_credits_limit,
                    "totalPlannedCredits": total_planned_credits,
                },
                suggested_fixes=[
                    "Increase maxCredits if policy allows a heavier semester",
                    "Move deferred courses to a future semester",
                ],
                related_course_ids=[
                    entry["courseId"]
                    for entry in skipped_due_to_workload
                    if entry.get("courseId")
                ],
            )
        )

    if total_planned_credits > max_credits_limit:
        risks.append(
            build_risk(
                risk_type="credit_overload",
                severity="high",
                title="Credit overload",
                explanation=(
                    f"The plan schedules {total_planned_credits} credits, which exceeds the "
                    f"workload limit of {max_credits_limit}."
                ),
                evidence={
                    "totalPlannedCredits": total_planned_credits,
                    "maxCredits": max_credits_limit,
                    "excessCredits": round_credits(total_planned_credits - max_credits_limit),
                },
                suggested_fixes=[
                    f"Reduce planned courses to {max_credits_limit} credits or fewer",
                    "Move lower-priority courses to a later semester",
                ],
                related_course_ids=planned_course_ids,
            )
        )

    if (
        min_credits_target > 0
        and total_planned_credits < min_credits_target
        and planned_courses
    ):
        risks.append(
            build_risk(
                risk_type="too_few_credits",
                severity="medium",
                title="Too few credits planned",
                explanation=(
                    f"The plan schedules {total_planned_credits} credits, below the minimum "
                    f"target of {min_credits_target}."
                ),
                evidence={
                    "totalPlannedCredits": total_planned_credits,
                    "minCredits": min_credits_target,
                    "shortfallCredits": round_credits(
                        min_credits_target - total_planned_credits
                    ),
                },
                suggested_fixes=[
                    "Add eligible mandatory or elective courses that satisfy prerequisites",
                    "Lower minCredits only if your degree policy allows a lighter semester",
                ],
            )
        )

    profile_max_credits = preferences.get("maxCreditsPerSemester")
    if (
        profile_max_credits is not None
        and total_planned_credits > round_credits(profile_max_credits)
        and total_planned_credits <= max_credits_limit
    ):
        risks.append(
            build_risk(
                risk_type="credit_overload",
                severity="medium",
                title="Exceeds preferred semester workload",
                explanation=(
                    f"The plan schedules {total_planned_credits} credits, above your profile "
                    f"preference of {profile_max_credits} credits per semester."
                ),
                evidence={
                    "totalPlannedCredits": total_planned_credits,
                    "profileMaxCreditsPerSemester": profile_max_credits,
                },
                suggested_fixes=[
                    "Align the plan with your preferred maxCreditsPerSemester setting",
                    "Update profile preferences if this workload is intentional",
                ],
                related_course_ids=planned_course_ids,
            )
        )

    if len(planned_course_ids) != len(unique_planned_course_ids):
        duplicate_ids = [
            course_id
            for index, course_id in enumerate(planned_course_ids)
            if course_id in planned_course_ids[:index]
        ]
        unique_duplicates = list(dict.fromkeys(duplicate_ids))
        risks.append(
            build_risk(
                risk_type="duplicate_planned_course",
                severity="medium",
                title="Duplicate courses in plan",
                explanation="The same course appears more than once in the planned semester.",
                evidence={"duplicateCourseIds": unique_duplicates},
                suggested_fixes=["Remove duplicate course entries from the semester plan"],
                related_course_ids=unique_duplicates,
            )
        )

    satisfied_prerequisite_ids = set(completed_course_ids)
    unknown_course_ids: list[str] = []
    out_of_scope_course_ids: list[str] = []

    for planned_course in planned_courses:
        course_id = normalize_course_id(planned_course["courseId"])

        if planned_course.get("catalogScopeValid") is False:
            out_of_scope_course_ids.append(course_id)
            continue

        catalog_course = courses_by_id.get(course_id)
        if not catalog_course:
            unknown_course_ids.append(course_id)
            continue

        number = course_number(catalog_course)
        title = course_title(catalog_course)

        if course_id in completed_course_ids:
            completion = effective_completions.get(course_id) or {}
            risks.append(
                build_risk(
                    risk_type="course_already_completed",
                    severity="high",
                    title="Course already completed",
                    explanation=f"{title} ({number}) is already completed with a passing grade.",
                    evidence={
                        "courseId": course_id,
                        "courseNumber": number,
                        "completedGrade": completion.get("grade"),
                    },
                    suggested_fixes=["Remove the completed course from the semester plan"],
                    related_course_ids=[course_id],
                )
            )

        if course_id in failed_attempts:
            failed_attempt = failed_attempts[course_id]
            risks.append(
                build_risk(
                    risk_type="failed_course_retake",
                    severity="medium",
                    title="Retaking a previously failed course",
                    explanation=(
                        f"{title} ({number}) has a prior failing attempt and is scheduled again."
                    ),
                    evidence={
                        "courseId": course_id,
                        "courseNumber": number,
                        "priorGrade": failed_attempt.get("grade"),
                        "priorSemesterCode": failed_attempt.get("semesterCode"),
                        "attempt": failed_attempt.get("attempt"),
                    },
                    suggested_fixes=[
                        "Confirm prerequisite preparation before retaking the course",
                        "Consider academic support resources for this course",
                    ],
                    related_course_ids=[course_id],
                )
            )

        if not prerequisites_met_for_course(catalog_course, satisfied_prerequisite_ids):
            missing_prerequisite_ids = [
                normalize_course_id(prerequisite_id)
                for prerequisite_id in (catalog_course.get("prerequisites") or [])
                if normalize_course_id(prerequisite_id) not in satisfied_prerequisite_ids
            ]
            risks.append(
                build_risk(
                    risk_type="unmet_prerequisites",
                    severity="high",
                    title="Unmet prerequisites",
                    explanation=(
                        f"{title} ({number}) is scheduled before its prerequisites are satisfied."
                    ),
                    evidence={
                        "courseId": course_id,
                        "courseNumber": number,
                        "missingPrerequisiteIds": missing_prerequisite_ids,
                        "missingPrerequisites": [
                            {
                                "courseId": prerequisite_id,
                                "courseNumber": course_number(
                                    courses_by_id.get(prerequisite_id)
                                ),
                                "courseTitle": course_title(
                                    courses_by_id.get(prerequisite_id)
                                ),
                            }
                            for prerequisite_id in missing_prerequisite_ids
                        ],
                    },
                    suggested_fixes=[
                        "Complete or schedule prerequisite courses before this course",
                        "Reorder the plan so prerequisites appear earlier in the semester",
                    ],
                    related_course_ids=[course_id, *missing_prerequisite_ids],
                )
            )

        satisfied_prerequisite_ids.add(course_id)

    if unknown_course_ids:
        risks.append(
            build_risk(
                risk_type="unknown_catalog_course",
                severity="high",
                title="Unknown catalog courses in plan",
                explanation=(
                    "One or more planned courses are not present in the published degree catalog."
                ),
                evidence={"unknownCourseIds": unknown_course_ids},
                suggested_fixes=[
                    "Replace unknown course ids with valid catalog courses for your degree"
                ],
                related_course_ids=unknown_course_ids,
            )
        )

    if out_of_scope_course_ids:
        risks.append(
            build_risk(
                risk_type="catalog_course_out_of_scope",
                severity="high",
                title="Courses outside active degree catalog scope",
                explanation=(
                    "One or more proposed courses are not part of the student's active "
                    "institution and catalog year."
                ),
                evidence={
                    "outOfScopeCourseIds": out_of_scope_course_ids,
                    "degreeInstitutionId": degree.get("institutionId"),
                    "degreeCatalogYear": degree.get("catalogYear"),
                },
                suggested_fixes=[
                    "Select courses from the catalog that matches your profile institution and catalog year",
                    "Update the student profile if you intentionally changed catalog scope",
                ],
                related_course_ids=out_of_scope_course_ids,
            )
        )

    planned_mandatory_count = sum(
        1
        for course in planned_courses
        if normalize_course_id(course["courseId"]) in remaining_mandatory_ids
    )

    remaining_mandatory = graduation_progress.get("remainingMandatoryCourses") or []
    all_planned_are_electives = bool(planned_courses) and all(
        course.get("category") == "elective"
        or normalize_course_id(course["courseId"]) in elective_pool_ids
        for course in planned_courses
    )

    if all_planned_are_electives and remaining_mandatory:
        risks.append(
            build_risk(
                risk_type="no_mandatory_progress",
                severity="medium",
                title="No mandatory degree progress in plan",
                explanation=(
                    "The plan includes only electives or non-mandatory courses while mandatory "
                    "degree requirements remain outstanding."
                ),
                evidence={
                    "remainingMandatoryCourseCount": len(remaining_mandatory),
                    "plannedCourseCount": len(planned_courses),
                },
                suggested_fixes=[
                    "Add remaining mandatory courses that satisfy prerequisites",
                    "Use the semester planner to prioritize mandatory requirements",
                ],
                related_course_ids=planned_course_ids,
            )
        )

    if (
        planned_courses
        and planned_mandatory_count == 0
        and remaining_mandatory
        and not all_planned_are_electives
    ):
        risks.append(
            build_risk(
                risk_type="insufficient_graduation_progress",
                severity="low",
                title="Limited graduation progress in plan",
                explanation=(
                    "The planned courses do not include any remaining mandatory degree requirements."
                ),
                evidence={
                    "remainingMandatoryCourseCount": len(remaining_mandatory),
                    "plannedMandatoryCount": planned_mandatory_count,
                },
                suggested_fixes=[
                    "Include at least one remaining mandatory course if prerequisites allow"
                ],
                related_course_ids=planned_course_ids,
            )
        )

    advanced_courses = [
        courses_by_id[normalize_course_id(course["courseId"])]
        for course in planned_courses
        if courses_by_id.get(normalize_course_id(course["courseId"]))
        and is_advanced_course(courses_by_id[normalize_course_id(course["courseId"])])
    ]

    if len(advanced_courses) >= 3:
        risks.append(
            build_risk(
                risk_type="too_many_advanced_courses",
                severity="medium",
                title="Heavy advanced course load",
                explanation=(
                    f"The plan includes {len(advanced_courses)} advanced-level courses in one semester."
                ),
                evidence={
                    "advancedCourseCount": len(advanced_courses),
                    "advancedCourses": [
                        {
                            "courseId": normalize_course_id(course["_id"]),
                            "courseNumber": course_number(course),
                            "courseTitle": course_title(course),
                            "level": course.get("level"),
                        }
                        for course in advanced_courses
                    ],
                },
                suggested_fixes=[
                    "Spread advanced courses across multiple semesters",
                    "Balance the schedule with lighter foundational courses",
                ],
                related_course_ids=[
                    normalize_course_id(course["_id"]) for course in advanced_courses
                ],
            )
        )

    summary = summarize_risks(risks)
    analysis_source = plan_view.get("analysisSource") or "semester_plan"

    return {
        "analyzerType": "deterministic",
        "semesterCode": plan_view.get("semesterCode"),
        "planId": plan_view.get("planId"),
        "analysisSource": analysis_source,
        "status": "open",
        "summary": summary,
        "risks": risks,
        "contextSnapshot": {
            "degreeId": normalize_course_id(degree["_id"]),
            "degreeCode": degree_code(degree),
            "catalogYear": degree.get("catalogYear"),
            "planPlannerType": plan_view.get("plannerType"),
            "analysisSource": analysis_source,
            "semesterCode": plan_view.get("semesterCode"),
            "totalPlannedCredits": total_planned_credits,
            "plannedCourseCount": len(planned_courses),
            "plannedCourseIds": planned_course_ids,
            "plannedCourses": [
                {
                    "courseId": normalize_course_id(course["courseId"]),
                    "courseNumber": course.get("courseNumber"),
                    "courseTitle": course.get("courseTitle"),
                    "credits": round_credits(course.get("credits") or 0),
                    "category": course.get("category"),
                }
                for course in planned_courses
            ],
            "maxCredits": max_credits_limit,
            "minCredits": min_credits_target,
            "profileMaxCreditsPerSemester": preferences.get("maxCreditsPerSemester"),
            "completedCourseCount": len(completed_course_ids),
            "remainingMandatoryCourseCount": len(remaining_mandatory),
            "graduationStatusSummary": graduation_progress.get("statusSummary"),
        },
    }
