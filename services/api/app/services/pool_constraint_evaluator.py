"""Evaluate course_pool sub-requirements (choose_n / choose_chain) for graduation progress."""

from __future__ import annotations

from typing import Any

from app.planning.prerequisite_resolver import canonical_course_number
from app.services.pool_chain_layouts import (
    FLEXIBLE_CHAIN_SUFFIXES,
    pool_chain_layout,
    pool_group_suffix,
)

DNE_STARRED_COURSE_NUMBERS: frozenset[str] = frozenset(
    {
        "0960222",
        "0960231",
        "0960235",
        "0960262",
        "0960324",
        "0960693",
        "0970135",
        "0970200",
        "0970215",
        "0970216",
        "0970222",
        "0970247",
        "0970248",
        "0970272",
        "0970400",
    }
)

DUAL_HASH_PROJECT_COURSE_NUMBERS: frozenset[str] = frozenset(DNE_STARRED_COURSE_NUMBERS)

PHYSICS_1 = "01140051"
PHYSICS_1M = "01140071"
ENGLISH_COURSE = "03240033"
ENGLISH_DEADLINE_SEMESTER_INDEX = 4

FACULTY_BUCKET_SUBREQUIREMENT_SUFFIXES: dict[str, tuple[str, ...]] = {
    "009009-1-000": (
        "ie-statistics-elective-chain",
        "ie-behavior-science-chain",
    ),
    "009118-1-000": ("is-behavior-science-chain",),
}

FOCUS_CHAIN_SUFFIX_PREFIXES: tuple[str, ...] = (
    "ie-focus-chain-",
    "is-focus-chain-",
)

ELECTIVE_DS_SUBREQUIREMENT_SUFFIXES: tuple[str, ...] = (
    "dne-starred-project-pool",
    "dual-hash-project-pool",
)


def _normalize_number(value: str | None) -> str | None:
    if not value:
        return None
    return canonical_course_number(str(value))


def _normalized_course_set(numbers: frozenset[str]) -> frozenset[str]:
    normalized: set[str] = set()
    for number in numbers:
        canonical = _normalize_number(number)
        if canonical:
            normalized.add(canonical)
    return frozenset(normalized)


DNE_STARRED_COURSE_NUMBERS_NORMALIZED = _normalized_course_set(DNE_STARRED_COURSE_NUMBERS)
DUAL_HASH_PROJECT_COURSE_NUMBERS_NORMALIZED = _normalized_course_set(DUAL_HASH_PROJECT_COURSE_NUMBERS)


def _pool_course_numbers(pool_document: dict[str, Any]) -> set[str]:
    numbers: set[str] = set()
    for ref in pool_document.get("courseReferences") or []:
        normalized = _normalize_number(ref.get("courseNumber"))
        if normalized:
            numbers.add(normalized)
    rule = pool_document.get("ruleExpression") or {}
    for prefix in rule.get("allowedPrefixes") or []:
        numbers.add(str(prefix))
    return numbers


def _course_matches_pool(
    course_number: str | None,
    pool_document: dict[str, Any],
) -> bool:
    normalized = _normalize_number(course_number)
    if not normalized:
        return False

    pool_numbers = _pool_course_numbers(pool_document)
    if normalized in pool_numbers:
        return True

    rule = pool_document.get("ruleExpression") or {}
    for prefix in rule.get("allowedPrefixes") or []:
        if normalized.startswith(str(prefix)):
            return True
    for extra in rule.get("alwaysIncludeCourseNumbers") or []:
        if normalized == _normalize_number(str(extra)):
            return True
    return False


def _completed_numbers_for_pool(
    pool_document: dict[str, Any],
    completed_courses: list[dict[str, Any]],
) -> set[str]:
    pool_group_id = str(pool_document.get("requirementGroupId") or "")
    matched: set[str] = set()
    for course in completed_courses:
        number = _normalize_number(course.get("courseNumber"))
        if not number:
            continue
        assigned_pool = course.get("assignedPoolGroupId")
        if assigned_pool and str(assigned_pool) == pool_group_id:
            matched.add(number)
            continue
        if assigned_pool:
            continue
        if _course_matches_pool(number, pool_document):
            matched.add(number)
    return matched


def _step_satisfied(step: dict[str, Any], completed_numbers: set[str]) -> bool:
    course_numbers = {_normalize_number(number) for number in step.get("courseNumbers") or []}
    course_numbers.discard(None)
    if step.get("kind") == "required":
        return bool(course_numbers & completed_numbers)
    if course_numbers:
        return bool(course_numbers & completed_numbers)
    return False


def _evaluate_structured_chain(
    pool_document: dict[str, Any],
    completed_numbers: set[str],
) -> tuple[bool, int, int]:
    layout = pool_chain_layout(pool_document)
    if layout is None:
        return False, 0, 0

    if layout["type"] == "steps":
        steps = layout.get("steps") or []
        required = len(steps)
        completed = sum(1 for step in steps if _step_satisfied(step, completed_numbers))
        return completed >= required, completed, required

    best_completed = 0
    best_required = 0
    for chain in layout.get("chains") or []:
        steps = chain.get("steps") or []
        required = len(steps)
        completed = sum(1 for step in steps if _step_satisfied(step, completed_numbers))
        if completed > best_completed:
            best_completed = completed
            best_required = required
    return best_completed >= best_required and best_required > 0, best_completed, best_required


def _evaluate_flexible_chain(
    pool_document: dict[str, Any],
    completed_numbers: set[str],
) -> tuple[bool, int, int]:
    rule = pool_document.get("ruleExpression") or {}
    required = int(rule.get("chooseCount") or 3)
    pool_numbers = _pool_course_numbers(pool_document)
    matched = completed_numbers & pool_numbers
    completed = len(matched)
    return completed >= required, completed, required


def evaluate_pool_constraint(
    pool_document: dict[str, Any],
    completed_courses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return satisfaction metadata for a single pool document."""
    rule = pool_document.get("ruleExpression") or {}
    operator = str(rule.get("operator") or "")
    completed_numbers = _completed_numbers_for_pool(pool_document, completed_courses)
    suffix = pool_group_suffix(str(pool_document.get("requirementGroupId") or ""))

    satisfied = False
    steps_completed = 0
    steps_required = 0

    if operator == "choose_n":
        steps_required = int(rule.get("chooseCount") or 1)
        pool_numbers = _pool_course_numbers(pool_document)
        if suffix == "dne-starred-project-pool" or rule.get("chain") == "dne_starred_projects":
            matched = completed_numbers & DNE_STARRED_COURSE_NUMBERS_NORMALIZED
        elif suffix == "dual-hash-project-pool" or rule.get("chain") == "dual_hash_projects":
            matched = completed_numbers & DUAL_HASH_PROJECT_COURSE_NUMBERS_NORMALIZED
        else:
            matched = completed_numbers & pool_numbers if pool_numbers else completed_numbers
        steps_completed = len(matched)
        satisfied = steps_completed >= steps_required
    elif operator == "choose_chain":
        if suffix in FLEXIBLE_CHAIN_SUFFIXES:
            satisfied, steps_completed, steps_required = _evaluate_flexible_chain(
                pool_document,
                completed_numbers,
            )
        else:
            satisfied, steps_completed, steps_required = _evaluate_structured_chain(
                pool_document,
                completed_numbers,
            )
    elif operator == "min_credits":
        min_credits = float(pool_document.get("minCredits") or rule.get("minCredits") or 0)
        credits = sum(
            float(course.get("creditsEarned") or 0)
            for course in completed_courses
            if _normalize_number(course.get("courseNumber")) in completed_numbers
        )
        steps_required = int(min_credits)
        steps_completed = int(credits)
        satisfied = credits >= min_credits
    else:
        satisfied = True

    status = "satisfied" if satisfied else ("in_progress" if steps_completed > 0 else "not_started")
    return {
        "requirementGroupId": pool_document.get("requirementGroupId"),
        "title": pool_document.get("title"),
        "operator": operator,
        "status": status,
        "stepsCompleted": steps_completed,
        "stepsRequired": steps_required,
        "satisfied": satisfied,
    }


def _is_focus_chain_pool(pool_document: dict[str, Any]) -> bool:
    suffix = pool_group_suffix(str(pool_document.get("requirementGroupId") or ""))
    rule = pool_document.get("ruleExpression") or {}
    return rule.get("operator") == "choose_chain" and any(
        suffix.startswith(prefix) for prefix in FOCUS_CHAIN_SUFFIX_PREFIXES
    )


def evaluate_bucket_pool_constraints(
    *,
    program_code: str,
    bucket_suffix: str,
    pool_documents: list[dict[str, Any]],
    completed_courses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate mandatory sub-pools for a credit bucket."""
    from app.services.graduation_requirement_links import credit_bucket_id_for_pool

    bucket_group = f"{program_code}:{bucket_suffix}"
    relevant_pools = [
        pool
        for pool in pool_documents
        if credit_bucket_id_for_pool(program_code=program_code, pool_document=pool) == bucket_group
    ]

    evaluations: list[dict[str, Any]] = []
    science_evaluation: dict[str, Any] | None = None
    for pool in relevant_pools:
        suffix = pool_group_suffix(str(pool.get("requirementGroupId") or ""))
        if suffix == "science-elective-supplement-pool":
            science_evaluation = evaluate_science_supplement(pool, completed_courses)
            evaluations.append(science_evaluation)
            continue
        evaluations.append(evaluate_pool_constraint(pool, completed_courses))

    mandatory_suffixes = FACULTY_BUCKET_SUBREQUIREMENT_SUFFIXES.get(program_code, ())
    mandatory_evaluations = [
        evaluation
        for evaluation in evaluations
        if pool_group_suffix(str(evaluation.get("requirementGroupId") or "")) in mandatory_suffixes
    ]
    focus_evaluations = [
        evaluation
        for pool in relevant_pools
        if _is_focus_chain_pool(pool)
        for evaluation in evaluations
        if str(evaluation.get("requirementGroupId")) == str(pool.get("requirementGroupId"))
    ]

    mandatory_ok = all(item["satisfied"] for item in mandatory_evaluations) if mandatory_evaluations else True
    focus_ok = any(item["satisfied"] for item in focus_evaluations) if focus_evaluations else True

    if bucket_suffix == "elective-ds":
        ds_evaluations = [
            evaluation
            for evaluation in evaluations
            if pool_group_suffix(str(evaluation.get("requirementGroupId") or ""))
            in ELECTIVE_DS_SUBREQUIREMENT_SUFFIXES
        ]
        ds_ok = all(item["satisfied"] for item in ds_evaluations) if ds_evaluations else True
    else:
        ds_ok = True

    science_ok = science_evaluation["satisfied"] if science_evaluation is not None else True
    constraints_satisfied = mandatory_ok and focus_ok and ds_ok and science_ok
    return {
        "constraintsSatisfied": constraints_satisfied,
        "mandatoryPools": mandatory_evaluations,
        "focusChains": focus_evaluations,
        "scienceSupplement": science_evaluation,
        "allPools": evaluations,
    }


def evaluate_science_supplement(
    pool_document: dict[str, Any],
    completed_courses: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate DDS science supplement credits with Physics 1 / 1M branching."""
    rule = pool_document.get("ruleExpression") or {}
    completed_numbers = {
        _normalize_number(course.get("courseNumber"))
        for course in completed_courses
        if course.get("courseNumber")
    }
    completed_numbers.discard(None)

    physics_1m = _normalize_number(str(rule.get("physics1mCourseNumber") or PHYSICS_1M))
    physics_1 = _normalize_number(str(rule.get("physics1CourseNumber") or PHYSICS_1))
    required = float(
        rule.get("supplementCreditsIfPhysics1m")
        if physics_1m in completed_numbers and physics_1 not in completed_numbers
        else pool_document.get("minCredits") or rule.get("minCredits") or 5.5
    )

    pool_numbers = _pool_course_numbers(pool_document)
    credits = 0.0
    for course in completed_courses:
        number = _normalize_number(course.get("courseNumber"))
        if number and number in pool_numbers:
            credits += float(course.get("creditsEarned") or 0)

    satisfied = credits >= required
    return {
        "requirementGroupId": pool_document.get("requirementGroupId"),
        "title": pool_document.get("title"),
        "status": "satisfied" if satisfied else ("in_progress" if credits > 0 else "not_started"),
        "creditsCompleted": round(credits, 2),
        "creditsRequired": required,
        "satisfied": satisfied,
        "usedPhysics1mRule": physics_1m in completed_numbers and physics_1 not in completed_numbers,
    }


def semester_index_from_code(semester_code: str, *, anchor_year: int, anchor_term: int) -> int | None:
    from app.services.completed_course_attempts import semester_code_rank

    year, term = semester_code_rank(semester_code)
    if year <= 0 or term <= 0:
        return None
    return (year - anchor_year) * 3 + (term - anchor_term) + 1


def build_advisory_warnings(
    *,
    program_code: str,
    completed_course_records: list[dict[str, Any]],
    catalog_courses_by_id: dict[str, dict[str, Any]] | None = None,
    current_semester_code: str | None = None,
) -> list[dict[str, Any]]:
    """Non-blocking catalog policy warnings (e.g. English within first 4 semesters)."""
    from app.services.completed_course_attempts import semester_code_rank

    warnings: list[dict[str, Any]] = []
    if not program_code.startswith("009") and program_code != "027396-1-000":
        return warnings

    def record_course_number(record: dict[str, Any]) -> str | None:
        number = record.get("courseNumber")
        if number:
            return _normalize_number(str(number))
        course_id = record.get("courseId")
        if course_id and catalog_courses_by_id:
            catalog_course = catalog_courses_by_id.get(str(course_id))
            if catalog_course:
                raw = catalog_course.get("courseNumber") or catalog_course.get("number")
                return _normalize_number(str(raw)) if raw else None
        return None

    english_records = [
        record
        for record in completed_course_records
        if record_course_number(record) == ENGLISH_COURSE
    ]
    ranked_semesters = [
        semester_code_rank(str(record.get("semesterCode") or ""))
        for record in completed_course_records
        if record.get("semesterCode")
    ]
    ranked_semesters = [item for item in ranked_semesters if item != (0, 0)]
    if not ranked_semesters:
        return warnings

    anchor_year, anchor_term = min(ranked_semesters)
    if english_records:
        english_semester = min(
            semester_code_rank(str(record.get("semesterCode") or "")) for record in english_records
        )
        english_index = semester_index_from_code(
            f"{english_semester[0]}-{english_semester[1]}",
            anchor_year=anchor_year,
            anchor_term=anchor_term,
        )
        if english_index is not None and english_index > ENGLISH_DEADLINE_SEMESTER_INDEX:
            warnings.append(
                {
                    "code": "english_deadline_late",
                    "severity": "warning",
                    "message": (
                        "Advanced Technical English B (3240033) should be completed within "
                        "the first 4 semesters."
                    ),
                    "courseNumber": ENGLISH_COURSE,
                    "completedSemesterIndex": english_index,
                }
            )
    else:
        reference_code = current_semester_code
        if reference_code:
            current_index = semester_index_from_code(
                reference_code,
                anchor_year=anchor_year,
                anchor_term=anchor_term,
            )
            if current_index is not None and current_index > ENGLISH_DEADLINE_SEMESTER_INDEX:
                warnings.append(
                    {
                        "code": "english_deadline_overdue",
                        "severity": "warning",
                        "message": (
                            "Advanced Technical English B (3240033) is required within "
                            "the first 4 semesters and is not yet completed."
                        ),
                        "courseNumber": ENGLISH_COURSE,
                        "currentSemesterIndex": current_index,
                    }
                )

    return warnings
