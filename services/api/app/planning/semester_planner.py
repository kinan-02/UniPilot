"""Deterministic semester planner — adapted for production DDS catalog shape."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.planning.prerequisite_resolver import (
    build_courses_by_number,
    resolve_prerequisite_ids,
)
from app.services.graduation_progress_calculator import (
    build_effective_completions,
    round_credits,
)
from app.services.graduation_requirement_links import (
    bucket_suffix_from_group_id,
    index_pools_by_linked_bucket,
    resolve_pool_for_bucket,
)

DEFAULT_MAX_CREDITS = 18.0
SEMESTER_MATRIX_GROUP_PATTERN = re.compile(r":semester-(\d+)-matrix")


def _matrix_semester_number(matrix_document: dict[str, Any]) -> int:
    rule = matrix_document.get("ruleExpression") or {}
    try:
        semester = rule.get("semester")
        if semester is not None:
            return int(semester)
    except (TypeError, ValueError):
        pass

    group_id = str(matrix_document.get("requirementGroupId") or "")
    match = SEMESTER_MATRIX_GROUP_PATTERN.search(group_id)
    if match:
        return int(match.group(1))

    return 999


def normalize_course_id(course_id: Any) -> str:
    return str(course_id)


def get_course_credits(course: dict[str, Any]) -> float:
    return round_credits(course.get("credits") or 0)


def prerequisites_met(course: dict[str, Any], satisfied_course_ids: set[str]) -> bool:
    prerequisite_ids = [
        normalize_course_id(course_id) for course_id in (course.get("prerequisites") or [])
    ]
    return all(course_id in satisfied_course_ids for course_id in prerequisite_ids)


def normalize_planner_course(
    course: dict[str, Any],
    *,
    courses_by_number: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "_id": course["_id"],
        "number": course.get("courseNumber") or course.get("number"),
        "title": course.get("title") or course.get("titleHebrew"),
        "credits": course.get("credits") or 0,
        "prerequisites": resolve_prerequisite_ids(course, courses_by_number=courses_by_number),
    }


def build_course_snapshot(course: dict[str, Any], *, category: str, reason: str) -> dict[str, Any]:
    return {
        "courseId": normalize_course_id(course["_id"]),
        "courseNumber": course.get("number"),
        "courseTitle": course.get("title"),
        "credits": get_course_credits(course),
        "category": category,
        "reason": reason,
    }


def sort_courses_by_number(courses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(courses, key=lambda course: str(course.get("number") or ""))


def resolve_catalog_course(
    courses_by_id: dict[str, dict[str, Any]],
    course_ref: dict[str, Any],
) -> dict[str, Any] | None:
    course_id = normalize_course_id(course_ref.get("courseId") or course_ref.get("_id"))
    return courses_by_id.get(course_id)


def _pool_course_numbers(pool_document: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for reference in pool_document.get("courseReferences") or []:
        number = reference.get("courseNumber")
        if number is not None:
            numbers.add(str(number))
    return numbers


def _pool_allowed_prefixes(pool_document: dict[str, Any]) -> list[str]:
    rule = pool_document.get("ruleExpression") or {}
    prefixes = rule.get("allowedPrefixes") or []
    return [str(prefix) for prefix in prefixes]


def _course_matches_pool(
    course: dict[str, Any],
    pool_document: dict[str, Any],
) -> bool:
    number = str(course.get("number") or "")
    if not number:
        return False

    allowed_numbers = _pool_course_numbers(pool_document)
    if allowed_numbers:
        return number in allowed_numbers

    prefixes = _pool_allowed_prefixes(pool_document)
    if prefixes:
        return any(number.startswith(prefix) for prefix in prefixes)

    return False


def _resolve_matrix_course(
    reference: dict[str, Any],
    *,
    courses_by_id: dict[str, dict[str, Any]],
    courses_by_number: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    course_id = reference.get("courseId")
    course_number = reference.get("courseNumber")
    if course_id is not None:
        return courses_by_id.get(normalize_course_id(course_id))
    if course_number is not None:
        raw = courses_by_number.get(str(course_number))
        if raw:
            return normalize_planner_course(raw, courses_by_number=courses_by_number)
    return None


def _mandatory_from_semester_matrix(
    semester_matrix_documents: list[dict[str, Any]],
    courses_by_id: dict[str, dict[str, Any]],
    courses_by_number: dict[str, dict[str, Any]],
    completed_course_ids: set[str],
) -> list[dict[str, Any]]:
    """Mandatory candidates from catalog semester matrix/table, ordered by semester then course number."""
    sorted_matrices = sorted(
        semester_matrix_documents,
        key=lambda document: (
            _matrix_semester_number(document),
            str(document.get("requirementGroupId") or ""),
        ),
    )

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for matrix_document in sorted_matrices:
        references = sorted(
            matrix_document.get("courseReferences") or [],
            key=lambda reference: str(reference.get("courseNumber") or reference.get("courseId") or ""),
        )
        for reference in references:
            course = _resolve_matrix_course(
                reference,
                courses_by_id=courses_by_id,
                courses_by_number=courses_by_number,
            )
            if course is None:
                continue
            course_id = normalize_course_id(course["_id"])
            if course_id in completed_course_ids or course_id in seen_ids:
                continue
            candidates.append(course)
            seen_ids.add(course_id)

    return candidates


def build_matrix_course_semester_index(
    semester_matrix_documents: list[dict[str, Any]],
) -> dict[str, int]:
    """Map course number to the earliest matrix semester that lists it."""
    index: dict[str, int] = {}
    for matrix_document in semester_matrix_documents:
        semester_number = _matrix_semester_number(matrix_document)
        for reference in matrix_document.get("courseReferences") or []:
            course_number = reference.get("courseNumber")
            if course_number is None:
                continue
            number = str(course_number)
            index[number] = min(index.get(number, semester_number), semester_number)
    return index


def resolve_active_matrix_semester(
    semester_matrix_documents: list[dict[str, Any]],
    *,
    courses_by_id: dict[str, dict[str, Any]],
    courses_by_number: dict[str, dict[str, Any]],
    completed_course_ids: set[str],
) -> int | None:
    """Earliest matrix semester that still has incomplete courses."""
    if not semester_matrix_documents:
        return None

    sorted_matrices = sorted(
        semester_matrix_documents,
        key=lambda document: _matrix_semester_number(document),
    )
    for matrix_document in sorted_matrices:
        semester_number = _matrix_semester_number(matrix_document)
        has_incomplete = False
        for reference in matrix_document.get("courseReferences") or []:
            course = _resolve_matrix_course(
                reference,
                courses_by_id=courses_by_id,
                courses_by_number=courses_by_number,
            )
            if course is None:
                continue
            if normalize_course_id(course["_id"]) not in completed_course_ids:
                has_incomplete = True
                break
        if has_incomplete:
            return semester_number
    return None


def partition_mandatory_by_matrix_semester(
    mandatory_candidates: list[dict[str, Any]],
    matrix_semester_index: dict[str, int],
) -> tuple[list[dict[str, Any]], dict[int, list[dict[str, Any]]]]:
    """Split mandatory candidates into degree-only refs and matrix semester buckets."""
    unmapped: list[dict[str, Any]] = []
    by_semester: dict[int, list[dict[str, Any]]] = {}
    for course in mandatory_candidates:
        course_number = str(course.get("number") or "")
        semester_number = matrix_semester_index.get(course_number)
        if semester_number is None:
            unmapped.append(course)
            continue
        by_semester.setdefault(semester_number, []).append(course)
    return unmapped, by_semester


def append_graduation_mandatory_candidates(
    mandatory_candidates: list[dict[str, Any]],
    *,
    graduation_progress: dict[str, Any],
    courses_by_id: dict[str, dict[str, Any]],
    completed_course_ids: set[str],
) -> list[dict[str, Any]]:
    """Add hard-requirement mandatory courses from graduation progress (deduped)."""
    seen_ids = {normalize_course_id(course["_id"]) for course in mandatory_candidates}
    extras: list[dict[str, Any]] = []

    for course_ref in graduation_progress.get("remainingMandatoryCourses") or []:
        course = resolve_catalog_course(courses_by_id, course_ref)
        if course is None:
            continue
        course_id = normalize_course_id(course["_id"])
        if course_id in completed_course_ids or course_id in seen_ids:
            continue
        extras.append(course)
        seen_ids.add(course_id)

    if not extras:
        return mandatory_candidates
    return sort_courses_by_number([*mandatory_candidates, *extras])


def matrix_semesters_for_planning(
    mandatory_by_semester: dict[int, list[dict[str, Any]]],
    *,
    active_semester: int | None,
    completed_course_ids: set[str],
) -> list[int]:
    """Choose which matrix semesters to draw from based on student progress."""
    if active_semester is None:
        return []

    available = sorted(
        semester for semester in mandatory_by_semester if semester >= active_semester
    )
    if not available:
        return []

    # Brand-new students: focus on the first incomplete matrix semester only.
    if not completed_course_ids and active_semester == available[0]:
        return [active_semester]

    return available


def _mandatory_from_course_references(
    hard_requirements: list[dict[str, Any]],
    courses_by_id: dict[str, dict[str, Any]],
    courses_by_number: dict[str, dict[str, Any]],
    completed_course_ids: set[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for requirement in hard_requirements:
        if not requirement.get("isMandatory", True):
            continue
        for reference in requirement.get("courseReferences") or []:
            course_id = reference.get("courseId")
            course_number = reference.get("courseNumber")
            course: dict[str, Any] | None = None
            if course_id is not None:
                course = courses_by_id.get(normalize_course_id(course_id))
            elif course_number is not None:
                raw = courses_by_number.get(str(course_number))
                if raw:
                    course = normalize_planner_course(raw, courses_by_number=courses_by_number)
            if course and normalize_course_id(course["_id"]) not in completed_course_ids:
                candidates.append(course)
    return sort_courses_by_number(candidates)


def _unsatisfied_elective_bucket_suffixes(
    graduation_progress: dict[str, Any],
    program_code: str,
) -> set[str]:
    suffixes: set[str] = set()
    for entry in graduation_progress.get("requirementProgress") or []:
        if entry.get("status") == "satisfied":
            continue
        group_id = str(entry.get("requirementGroupId") or "")
        suffix = bucket_suffix_from_group_id(group_id, program_code)
        requirement_type = entry.get("requirementType")
        if requirement_type == "elective" or suffix.startswith("elective"):
            suffixes.add(suffix)
    return suffixes


def _has_remaining_elective_need(
    graduation_progress: dict[str, Any],
    program_code: str,
) -> bool:
    if float(graduation_progress.get("remainingElectiveCredits") or 0) > 0:
        return True
    return bool(_unsatisfied_elective_bucket_suffixes(graduation_progress, program_code))


def _elective_from_pools(
    *,
    graduation_progress: dict[str, Any],
    pool_documents: list[dict[str, Any]],
    hard_requirements: list[dict[str, Any]],
    program_code: str,
    catalog_courses: list[dict[str, Any]],
    completed_course_ids: set[str],
) -> list[dict[str, Any]]:
    if not _has_remaining_elective_need(graduation_progress, program_code):
        return []

    pools_by_id = {
        str(document["requirementGroupId"]): document
        for document in pool_documents
        if document.get("requirementGroupId")
    }
    pools_by_linked_bucket = index_pools_by_linked_bucket(pool_documents)
    unsatisfied_elective_suffixes = _unsatisfied_elective_bucket_suffixes(
        graduation_progress,
        program_code,
    )

    normalized_catalog = [
        normalize_planner_course(course, courses_by_number=build_courses_by_number(catalog_courses))
        for course in catalog_courses
    ]

    candidates: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for requirement in hard_requirements:
        suffix = bucket_suffix_from_group_id(
            str(requirement.get("requirementGroupId") or ""),
            program_code,
        )
        if suffix not in unsatisfied_elective_suffixes:
            continue

        pool_document, _, _ = resolve_pool_for_bucket(
            program_code=program_code,
            bucket_suffix=suffix,
            pools_by_group_id=pools_by_id,
            pools_by_linked_bucket=pools_by_linked_bucket,
        )
        if not pool_document:
            continue

        for course in normalized_catalog:
            course_id = normalize_course_id(course["_id"])
            if course_id in completed_course_ids or course_id in seen_ids:
                continue
            if _course_matches_pool(course, pool_document):
                candidates.append(course)
                seen_ids.add(course_id)

    return sort_courses_by_number(candidates)


def build_candidate_pools(
    *,
    catalog_courses: list[dict[str, Any]],
    graduation_progress: dict[str, Any],
    hard_requirements: list[dict[str, Any]] | None = None,
    pool_documents: list[dict[str, Any]] | None = None,
    semester_matrix_documents: list[dict[str, Any]] | None = None,
    program_code: str | None = None,
    completed_course_ids: set[str],
) -> dict[str, Any]:
    courses_by_number = build_courses_by_number(catalog_courses)
    normalized_courses = [
        normalize_planner_course(course, courses_by_number=courses_by_number)
        for course in catalog_courses
    ]
    courses_by_id = {
        normalize_course_id(course["_id"]): course for course in normalized_courses
    }

    mandatory_candidates: list[dict[str, Any]] = []
    if semester_matrix_documents:
        mandatory_candidates = _mandatory_from_semester_matrix(
            semester_matrix_documents,
            courses_by_id,
            courses_by_number,
            completed_course_ids,
        )

    if not mandatory_candidates:
        mandatory_remaining_refs = graduation_progress.get("remainingMandatoryCourses") or []
        mandatory_candidates = sort_courses_by_number(
            [
                course
                for course_ref in mandatory_remaining_refs
                if (course := resolve_catalog_course(courses_by_id, course_ref)) is not None
                and normalize_course_id(course["_id"]) not in completed_course_ids
            ]
        )

    if not mandatory_candidates and hard_requirements:
        mandatory_candidates = _mandatory_from_course_references(
            hard_requirements,
            courses_by_id,
            courses_by_number,
            completed_course_ids,
        )
    elif mandatory_candidates:
        mandatory_candidates = append_graduation_mandatory_candidates(
            mandatory_candidates,
            graduation_progress=graduation_progress,
            courses_by_id=courses_by_id,
            completed_course_ids=completed_course_ids,
        )

    elective_remaining_refs: list[dict[str, Any]] = []
    for entry in graduation_progress.get("requirementProgress") or []:
        if entry.get("requirementType") != "elective":
            continue
        elective_remaining_refs.extend(entry.get("remainingCourses") or [])

    elective_candidates = sort_courses_by_number(
        [
            course
            for course_ref in elective_remaining_refs
            if (course := resolve_catalog_course(courses_by_id, course_ref)) is not None
            and normalize_course_id(course["_id"]) not in completed_course_ids
        ]
    )

    if not elective_candidates and hard_requirements and pool_documents and program_code:
        elective_candidates = _elective_from_pools(
            graduation_progress=graduation_progress,
            pool_documents=pool_documents,
            hard_requirements=hard_requirements,
            program_code=program_code,
            catalog_courses=catalog_courses,
            completed_course_ids=completed_course_ids,
        )

    return {
        "coursesById": courses_by_id,
        "mandatoryCandidates": mandatory_candidates,
        "electiveCandidates": elective_candidates,
    }


def describe_missing_prerequisites(
    course: dict[str, Any],
    satisfied_course_ids: set[str],
    courses_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    missing_prerequisite_ids = [
        normalize_course_id(course_id)
        for course_id in (course.get("prerequisites") or [])
        if normalize_course_id(course_id) not in satisfied_course_ids
    ]

    missing_prerequisites = []
    for course_id in missing_prerequisite_ids:
        prerequisite_course = courses_by_id.get(course_id)
        missing_prerequisites.append(
            {
                "courseId": course_id,
                "courseNumber": (prerequisite_course or {}).get("number"),
                "courseTitle": (prerequisite_course or {}).get("title"),
            }
        )

    labels = [
        entry["courseNumber"] or entry["courseId"]
        for entry in missing_prerequisites
        if entry.get("courseNumber") or entry.get("courseId")
    ]
    reason = (
        f"Blocked until prerequisite course(s) are completed or scheduled earlier: {', '.join(labels)}"
        if labels
        else "Blocked by unsatisfied prerequisites"
    )

    return {
        "missingPrerequisiteIds": missing_prerequisite_ids,
        "missingPrerequisites": missing_prerequisites,
        "reason": reason,
    }


def collect_blocked_courses(
    candidates: list[dict[str, Any]],
    satisfied_course_ids: set[str],
    courses_by_id: dict[str, dict[str, Any]],
    *,
    category: str,
) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for course in candidates:
        if prerequisites_met(course, satisfied_course_ids):
            continue
        details = describe_missing_prerequisites(course, satisfied_course_ids, courses_by_id)
        blocked.append(
            {
                "courseId": normalize_course_id(course["_id"]),
                "courseNumber": course.get("number"),
                "courseTitle": course.get("title"),
                "category": category,
                **details,
            }
        )
    return blocked


def build_workload_skip(course: dict[str, Any], course_credits: float) -> dict[str, Any]:
    return {
        "courseId": normalize_course_id(course["_id"]),
        "courseNumber": course.get("number"),
        "courseTitle": course.get("title"),
        "credits": course_credits,
        "reason": "Would exceed maxCredits workload limit",
    }


def select_courses_from_candidates(
    *,
    candidates: list[dict[str, Any]],
    satisfied_course_ids: set[str],
    max_credits_limit: float,
    starting_credits: float,
    category: str,
    default_reason: str,
) -> dict[str, Any]:
    selected_courses: list[dict[str, Any]] = []
    skipped_due_to_workload: list[dict[str, Any]] = []
    remaining = list(candidates)
    total_credits = starting_credits

    progressed = True
    while progressed and remaining and total_credits < max_credits_limit:
        progressed = False
        index = 0
        while index < len(remaining):
            course = remaining[index]
            if not prerequisites_met(course, satisfied_course_ids):
                index += 1
                continue

            course_credits = get_course_credits(course)
            if total_credits + course_credits > max_credits_limit:
                skipped_due_to_workload.append(build_workload_skip(course, course_credits))
                remaining.pop(index)
                continue

            selected_courses.append(
                build_course_snapshot(course, category=category, reason=default_reason)
            )
            satisfied_course_ids.add(normalize_course_id(course["_id"]))
            total_credits = round_credits(total_credits + course_credits)
            remaining.pop(index)
            progressed = True

    return {
        "selectedCourses": selected_courses,
        "skippedDueToWorkload": skipped_due_to_workload,
        "remaining": remaining,
        "totalCredits": total_credits,
    }


def can_add_another_course(
    candidates: list[dict[str, Any]],
    satisfied_course_ids: set[str],
    remaining_credits: float,
    selected_course_ids: set[str],
) -> bool:
    for course in candidates:
        course_id = normalize_course_id(course["_id"])
        if course_id in selected_course_ids:
            continue
        if prerequisites_met(course, satisfied_course_ids) and get_course_credits(course) <= remaining_credits:
            return True
    return False


def build_plan_summary(
    *,
    empty_plan: bool,
    partial_plan: bool,
    semester_code: str,
    selected_count: int,
    min_credits_target: float,
    total_credits: float,
    max_credits_limit: float,
    blocked_count: int,
    skipped_workload_count: int,
) -> str:
    if empty_plan:
        if blocked_count > 0:
            return (
                "No eligible courses are available because remaining courses are "
                "blocked by unsatisfied prerequisites"
            )
        return "No eligible courses are available for the requested semester workload"

    if partial_plan:
        if min_credits_target > 0 and total_credits < min_credits_target:
            return (
                f"Partial plan generated because workload limits prevented reaching "
                f"minCredits ({total_credits}/{min_credits_target})"
            )
        if total_credits < max_credits_limit:
            if skipped_workload_count > 0 or blocked_count > 0:
                return (
                    f"Partial plan generated because only {selected_count} course(s) fit "
                    f"within maxCredits ({total_credits}/{max_credits_limit})"
                )
            return (
                f"Partial plan generated because no additional eligible courses were "
                f"available below maxCredits ({total_credits}/{max_credits_limit})"
            )

    return f"Recommended {selected_count} course(s) for {semester_code}"


def generate_deterministic_semester_plan(
    *,
    profile: dict[str, Any],
    degree: dict[str, Any],
    catalog_courses: list[dict[str, Any]],
    graduation_progress: dict[str, Any],
    completed_course_records: list[dict[str, Any]],
    semester_code: str,
    max_credits: float | None = None,
    min_credits: float | None = None,
    name: str | None = None,
    hard_requirements: list[dict[str, Any]] | None = None,
    pool_documents: list[dict[str, Any]] | None = None,
    semester_matrix_documents: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    effective_completions = build_effective_completions(completed_course_records)
    completed_course_ids = set(effective_completions.keys())
    satisfied_course_ids = set(completed_course_ids)

    preferences = profile.get("preferences") or {}
    max_credits_limit = round_credits(
        max_credits if max_credits is not None else preferences.get("maxCreditsPerSemester", DEFAULT_MAX_CREDITS)
    )
    min_credits_target = round_credits(min_credits or 0)

    program_code = str(degree.get("programCode") or degree.get("code") or "")
    pools = build_candidate_pools(
        catalog_courses=catalog_courses,
        graduation_progress=graduation_progress,
        hard_requirements=hard_requirements,
        pool_documents=pool_documents,
        semester_matrix_documents=semester_matrix_documents,
        program_code=program_code or None,
        completed_course_ids=completed_course_ids,
    )
    courses_by_id = pools["coursesById"]
    mandatory_candidates = pools["mandatoryCandidates"]
    elective_candidates = pools["electiveCandidates"]

    mandatory_selection = select_courses_from_candidates(
        candidates=mandatory_candidates,
        satisfied_course_ids=satisfied_course_ids,
        max_credits_limit=max_credits_limit,
        starting_credits=0,
        category="mandatory",
        default_reason="Remaining mandatory course from degree semester matrix",
    )

    selected_courses = list(mandatory_selection["selectedCourses"])
    skipped_due_to_workload = list(mandatory_selection["skippedDueToWorkload"])
    total_credits = mandatory_selection["totalCredits"]

    selected_course_ids = {course["courseId"] for course in selected_courses}
    remaining_mandatory_credits = round_credits(max_credits_limit - total_credits)
    can_add_mandatory = can_add_another_course(
        mandatory_candidates,
        satisfied_course_ids,
        remaining_mandatory_credits,
        selected_course_ids,
    )

    should_include_electives = (
        total_credits < max_credits_limit
        and len(elective_candidates) > 0
        and (not can_add_mandatory or total_credits < min_credits_target)
    )

    if should_include_electives:
        elective_reason = (
            "Elective selected to approach minCredits target"
            if total_credits < min_credits_target
            else "Elective selected after mandatory priorities"
        )
        elective_selection = select_courses_from_candidates(
            candidates=elective_candidates,
            satisfied_course_ids=satisfied_course_ids,
            max_credits_limit=max_credits_limit,
            starting_credits=total_credits,
            category="elective",
            default_reason=elective_reason,
        )
        selected_courses.extend(elective_selection["selectedCourses"])
        skipped_due_to_workload.extend(elective_selection["skippedDueToWorkload"])
        total_credits = elective_selection["totalCredits"]

    final_selected_ids = {course["courseId"] for course in selected_courses}
    unselected_mandatory = [
        course
        for course in mandatory_candidates
        if normalize_course_id(course["_id"]) not in final_selected_ids
    ]
    unselected_electives = [
        course
        for course in elective_candidates
        if normalize_course_id(course["_id"]) not in final_selected_ids
    ]

    blocked_mandatory = collect_blocked_courses(
        unselected_mandatory,
        satisfied_course_ids,
        courses_by_id,
        category="mandatory",
    )
    blocked_electives = collect_blocked_courses(
        unselected_electives,
        satisfied_course_ids,
        courses_by_id,
        category="elective",
    )
    blocked_by_prerequisites = blocked_mandatory + blocked_electives

    meets_min_credits = total_credits >= min_credits_target or len(selected_courses) == 0
    empty_plan = len(selected_courses) == 0
    partial_plan = len(selected_courses) > 0 and (
        (min_credits_target > 0 and total_credits < min_credits_target)
        or total_credits < max_credits_limit
    )

    rules_applied = [
        "Exclude courses already completed with a passing grade",
        "Exclude failed attempts from completed-course eligibility",
        "Use catalog semester matrix/table courses as mandatory planning candidates",
        "Prioritize earlier catalog semesters before later semesters in the matrix",
        "Prioritize remaining mandatory courses before electives",
        (
            "Recommend only courses with satisfied prerequisites (completed or scheduled "
            "earlier in the same plan)"
        ),
        "Respect maxCredits workload limit",
        "Use profile preferred workload when maxCredits is not provided",
    ]
    if min_credits_target > 0:
        rules_applied.append("Attempt to reach minCredits when capacity allows")

    explanation = {
        "summary": build_plan_summary(
            empty_plan=empty_plan,
            partial_plan=partial_plan,
            semester_code=semester_code,
            selected_count=len(selected_courses),
            min_credits_target=min_credits_target,
            total_credits=total_credits,
            max_credits_limit=max_credits_limit,
            blocked_count=len(blocked_by_prerequisites),
            skipped_workload_count=len(skipped_due_to_workload),
        ),
        "rulesApplied": rules_applied,
        "semesterCode": semester_code,
        "maxCredits": max_credits_limit,
        "minCredits": min_credits_target,
        "profileMaxCreditsPerSemester": preferences.get("maxCreditsPerSemester"),
        "totalRecommendedCredits": total_credits,
        "selectedCount": len(selected_courses),
        "mandatoryRemainingBeforePlan": len(mandatory_candidates),
        "completedCoursesExcluded": len(completed_course_ids),
        "blockedByPrerequisites": blocked_by_prerequisites,
        "skippedDueToWorkload": skipped_due_to_workload,
        "partialPlan": partial_plan,
        "emptyPlan": empty_plan,
        "meetsMinCredits": meets_min_credits,
        "meetsMaxCredits": total_credits >= max_credits_limit or len(selected_courses) == 0,
    }

    degree_code = degree.get("programCode") or degree.get("code")
    plan_name = (
        name
        or f"Generated plan for {semester_code} ({degree_code}, "
        f"{datetime.now(timezone.utc).date().isoformat()})"
    )

    return {
        "name": plan_name,
        "status": "draft",
        "version": 1,
        "plannerType": "deterministic",
        "assumptions": {
            "generatedBy": "deterministic-semester-planner",
            "semesterCode": semester_code,
            "maxCredits": max_credits_limit,
            "minCredits": min_credits_target,
            "degreeId": normalize_course_id(degree["_id"]),
            "catalogYear": degree.get("catalogYear"),
            "catalogVersion": degree.get("catalogVersion"),
            "graduationStatusSummary": graduation_progress.get("statusSummary"),
            "mandatorySource": (
                "semester_matrix"
                if semester_matrix_documents
                else "graduation_progress_fallback"
            ),
            "semesterMatrixRuleCount": len(semester_matrix_documents or []),
        },
        "explanation": explanation,
        "semesters": [
            {
                "semesterCode": semester_code,
                "goalCredits": max_credits_limit,
                "order": 1,
                "plannedCourses": selected_courses,
                "notes": explanation["summary"],
                "constraintsSnapshot": {
                    "maxCredits": max_credits_limit,
                    "minCredits": min_credits_target,
                    "profileMaxCreditsPerSemester": preferences.get("maxCreditsPerSemester"),
                },
            }
        ],
    }
