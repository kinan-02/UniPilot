"""Deterministic graduation progress calculator (Phase 15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.graduation_requirement_links import (
    bucket_suffix_from_group_id,
    index_pools_by_linked_bucket,
    resolve_pool_for_bucket,
)

from app.services.grade_evaluation import is_passing_grade, resolve_record_numeric_grade

# Buckets with strict pool enforcement first, then general credit buckets.
BUCKET_EVALUATION_ORDER = (
    "elective-ds",
    "elective-faculty",
    "elective-general",
    "enrichment",
    "free-elective",
    "physical-education",
    "core-mandatory",
)


def round_credits(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def round_percentage(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def normalize_id(value: Any) -> str:
    return str(value)


def _recorded_at_timestamp(value: Any) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, str):
        try:
            normalized = value.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def build_effective_completions(
    completed_course_records: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    best_by_course_id: dict[str, dict[str, Any]] = {}

    for record in completed_course_records:
        if not is_passing_grade(record):
            continue

        course_id = normalize_id(record["courseId"])
        numeric_grade = resolve_record_numeric_grade(record)
        candidate = {
            "courseId": course_id,
            "creditsEarned": round_credits(record["creditsEarned"]),
            "grade": numeric_grade if numeric_grade is not None else record.get("grade"),
            "semesterCode": record.get("semesterCode"),
            "recordedAt": record.get("recordedAt"),
        }

        existing = best_by_course_id.get(course_id)
        if not existing:
            best_by_course_id[course_id] = candidate
            continue

        if candidate["creditsEarned"] > existing["creditsEarned"]:
            best_by_course_id[course_id] = candidate
            continue

        if candidate["creditsEarned"] == existing["creditsEarned"]:
            if _recorded_at_timestamp(candidate.get("recordedAt")) > _recorded_at_timestamp(
                existing.get("recordedAt")
            ):
                best_by_course_id[course_id] = candidate

    return best_by_course_id


def build_course_progress_entry(
    course_id: str,
    catalog_course: dict[str, Any] | None,
    completion: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "courseId": course_id,
        "courseNumber": (catalog_course or {}).get("courseNumber") or (catalog_course or {}).get("number"),
        "courseTitle": (catalog_course or {}).get("title") or (catalog_course or {}).get("titleHebrew"),
        "catalogCredits": (catalog_course or {}).get("credits"),
        "creditsEarned": completion["creditsEarned"] if completion else None,
        "grade": completion.get("grade") if completion else None,
        "semesterCode": completion.get("semesterCode") if completion else None,
    }


def _pool_course_numbers(pool_document: dict[str, Any] | None) -> set[str]:
    if not pool_document:
        return set()
    numbers: set[str] = set()
    for ref in pool_document.get("courseReferences") or []:
        number = ref.get("courseNumber")
        if number:
            numbers.add(str(number))
    return numbers


def _pool_allowed_prefixes(pool_document: dict[str, Any] | None) -> list[str]:
    if not pool_document:
        return []
    rule = pool_document.get("ruleExpression") or {}
    prefixes = rule.get("allowedPrefixes") or []
    return [str(prefix) for prefix in prefixes]


def is_course_eligible_for_pool(
    course_number: str | None,
    pool_document: dict[str, Any] | None,
) -> bool:
    if not pool_document or not course_number:
        return False

    rule = pool_document.get("ruleExpression") or {}
    if rule.get("type") != "course_pool":
        return False

    allowed_numbers = _pool_course_numbers(pool_document)
    if allowed_numbers:
        return course_number in allowed_numbers

    prefixes = _pool_allowed_prefixes(pool_document)
    if prefixes:
        return any(course_number.startswith(prefix) for prefix in prefixes)

    return False


def _requirement_group_suffix(requirement: dict[str, Any], program_code: str) -> str:
    group_id = requirement.get("requirementGroupId") or ""
    return bucket_suffix_from_group_id(str(group_id), program_code)


def _index_pools_by_group_id(pool_documents: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for document in pool_documents:
        group_id = document.get("requirementGroupId")
        if group_id:
            indexed[str(group_id)] = document
    return indexed


def _index_buckets(requirements: list[dict[str, Any]], program_code: str) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for requirement in requirements:
        rule_type = (requirement.get("ruleExpression") or {}).get("type")
        if rule_type != "credit_bucket":
            continue
        suffix = _requirement_group_suffix(requirement, program_code)
        buckets[suffix] = requirement
    return buckets


def _dedupe_courses_by_id(course_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for entry in course_entries:
        course_id = entry["courseId"]
        if course_id not in by_id:
            by_id[course_id] = entry
    return list(by_id.values())


def _build_status_summary(
    completed_credits: float,
    missing_requirements: list[dict[str, Any]],
) -> str:
    if completed_credits <= 0:
        return "not_started"
    if not missing_requirements:
        return "complete"
    if not any(item.get("isMandatory") for item in missing_requirements):
        return "mandatory_requirements_met"
    return "in_progress"


def calculate_graduation_progress(
    *,
    degree_program: dict[str, Any],
    hard_requirements: list[dict[str, Any]],
    pool_documents: list[dict[str, Any]],
    catalog_courses_by_id: dict[str, dict[str, Any]],
    completed_course_records: list[dict[str, Any]],
) -> dict[str, Any]:
    program_code = str(degree_program["programCode"])
    pools_by_id = _index_pools_by_group_id(pool_documents)
    pools_by_linked_bucket = index_pools_by_linked_bucket(pool_documents)
    buckets_by_suffix = _index_buckets(hard_requirements, program_code)

    effective_completions = build_effective_completions(completed_course_records)
    assigned_course_ids: set[str] = set()
    ineligible_credits: list[dict[str, Any]] = []
    requirement_progress: list[dict[str, Any]] = []

    ordered_suffixes = [
        suffix for suffix in BUCKET_EVALUATION_ORDER if suffix in buckets_by_suffix
    ]
    for suffix in buckets_by_suffix:
        if suffix not in ordered_suffixes:
            ordered_suffixes.append(suffix)

    for suffix in ordered_suffixes:
        requirement = buckets_by_suffix[suffix]
        min_credits = float(requirement.get("minCredits") or 0)
        pool_document, pool_group, strict_pool = resolve_pool_for_bucket(
            program_code=program_code,
            bucket_suffix=suffix,
            pools_by_group_id=pools_by_id,
            pools_by_linked_bucket=pools_by_linked_bucket,
        )

        completed_courses: list[dict[str, Any]] = []
        remaining_courses: list[dict[str, Any]] = []
        credits_completed = 0.0

        for course_id, completion in sorted(
            effective_completions.items(),
            key=lambda item: item[0],
        ):
            if course_id in assigned_course_ids:
                continue

            catalog_course = catalog_courses_by_id.get(course_id)
            course_number = None
            if catalog_course:
                course_number = catalog_course.get("courseNumber") or catalog_course.get("number")
                if course_number is not None:
                    course_number = str(course_number)

            entry = build_course_progress_entry(course_id, catalog_course, completion)

            if strict_pool:
                if is_course_eligible_for_pool(course_number, pool_document):
                    completed_courses.append(entry)
                    credits_completed += completion["creditsEarned"]
                    assigned_course_ids.add(course_id)
                elif course_number is not None:
                    ineligible_credits.append(
                        {
                            "courseId": course_id,
                            "courseNumber": course_number,
                            "creditsEarned": completion["creditsEarned"],
                            "reason": "not_in_linked_pool",
                            "linkedPoolGroupId": pool_group,
                            "bucketSuffix": suffix,
                        }
                    )
                continue

            if credits_completed >= min_credits:
                break

            completed_courses.append(entry)
            credits_completed += completion["creditsEarned"]
            assigned_course_ids.add(course_id)

        credits_completed = round_credits(credits_completed)

        satisfied = credits_completed >= min_credits
        if satisfied:
            status = "satisfied"
        elif credits_completed > 0:
            status = "in_progress"
        else:
            status = "not_started"

        requirement_progress.append(
            {
                "requirementId": normalize_id(requirement.get("_id", requirement.get("requirementGroupId"))),
                "requirementGroupId": requirement.get("requirementGroupId"),
                "title": requirement.get("title"),
                "requirementType": requirement.get("requirementType"),
                "isMandatory": bool(requirement.get("isMandatory", True)),
                "requirementEnforcement": "hard",
                "eligibilityEnforcement": "strict_pool" if strict_pool else "credit_bucket_only",
                "linkedPoolGroupId": pool_group,
                "status": status,
                "minCredits": min_credits,
                "creditsCompleted": credits_completed,
                "creditsRemaining": 0 if satisfied else round_credits(max(0, min_credits - credits_completed)),
                "completedCourses": completed_courses,
                "remainingCourses": remaining_courses,
            }
        )

    total_required_credits = float(
        degree_program.get("totalCredits")
        or sum(float(r.get("minCredits") or 0) for r in buckets_by_suffix.values())
    )
    completed_credits = round_credits(
        sum(completion["creditsEarned"] for completion in effective_completions.values())
    )
    credits_remaining = round_credits(max(0, total_required_credits - completed_credits))
    completion_percentage = (
        round_percentage(min(100, (completed_credits / total_required_credits) * 100))
        if total_required_credits > 0
        else 0.0
    )

    mandatory_progress = [entry for entry in requirement_progress if entry["isMandatory"]]
    elective_progress = [entry for entry in requirement_progress if not entry["isMandatory"]]

    completed_mandatory_courses = _dedupe_courses_by_id(
        [course for entry in mandatory_progress for course in entry["completedCourses"]]
    )
    remaining_mandatory_courses = _dedupe_courses_by_id(
        [course for entry in mandatory_progress for course in entry["remainingCourses"]]
    )
    completed_mandatory_ids = {course["courseId"] for course in completed_mandatory_courses}
    remaining_mandatory_courses = [
        course for course in remaining_mandatory_courses if course["courseId"] not in completed_mandatory_ids
    ]

    elective_credits_required = round_credits(
        sum(float(entry["minCredits"] or 0) for entry in elective_progress)
    )
    completed_elective_credits = round_credits(
        sum(float(entry["creditsCompleted"] or 0) for entry in elective_progress)
    )
    remaining_elective_credits = round_credits(
        max(0, elective_credits_required - completed_elective_credits)
    )

    missing_requirements = [
        {
            "requirementId": entry["requirementId"],
            "requirementGroupId": entry["requirementGroupId"],
            "title": entry["title"],
            "requirementType": entry["requirementType"],
            "isMandatory": entry["isMandatory"],
            "status": entry["status"],
            "creditsCompleted": entry["creditsCompleted"],
            "creditsRequired": entry["minCredits"],
            "creditsRemaining": entry["creditsRemaining"],
            "remainingCourseCount": len(entry["remainingCourses"]),
            "eligibilityEnforcement": entry["eligibilityEnforcement"],
        }
        for entry in requirement_progress
        if entry["status"] != "satisfied"
    ]

    assumptions = [
        "Hard requirements from degree_requirements only; semester_matrix rules are planning-only.",
        "course_pool eligibility enforced for linked elective buckets (explicit link or naming convention).",
        "Passing numeric grades strictly above 55 count toward progress; 55 and below are excluded.",
        "Track-specific requirements excluded until student track is selected on profile.",
    ]

    return {
        "degreeId": normalize_id(degree_program["_id"]),
        "degreeCode": program_code,
        "degreeName": degree_program.get("name"),
        "catalogYear": degree_program.get("catalogYear"),
        "catalogVersion": degree_program.get("catalogVersion"),
        "completedCredits": completed_credits,
        "totalRequiredCredits": round_credits(total_required_credits),
        "creditsRemaining": credits_remaining,
        "completionPercentage": completion_percentage,
        "completedMandatoryCourses": completed_mandatory_courses,
        "remainingMandatoryCourses": remaining_mandatory_courses,
        "completedElectiveCredits": completed_elective_credits,
        "remainingElectiveCredits": remaining_elective_credits,
        "requirementProgress": requirement_progress,
        "missingRequirements": missing_requirements,
        "ineligibleCredits": ineligible_credits,
        "assumptions": assumptions,
        "statusSummary": _build_status_summary(completed_credits, missing_requirements),
    }
