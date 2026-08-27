"""DB wiring for the term-plan orchestration behind the agent's `plan_term` tool.

Loads the student's planning context, resolves the agent-supplied candidate course
numbers against the catalog, loads the offerings for each requested term, and calls
the pure `plan_terms`. Deliberately SELF-CONTAINED -- it does not import from the
legacy `semester_plan_suggestion_service` (which is being retired); the only shared
pieces are the planning-context loader, the catalog repository, and the pure engine.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.planning.prerequisite_resolver import build_courses_by_number, canonical_course_number
from app.planning.semester_codes import resolve_plan_term
from app.planning.term_plan import Candidate, TermInput, plan_terms
from app.repositories import catalog_repository
from app.services.catalog_overlap_groups import build_catalog_overlap_groups
from app.services.graduation_progress_calculator import build_effective_completions, round_credits
from app.services.semester_plan_service import load_planning_context

DEFAULT_MAX_CREDITS = 18.0
MAX_CREDITS_CEILING = 40.0
VALID_CATEGORIES = frozenset({"mandatory", "elective"})


async def build_term_plan(
    database: AsyncIOMotorDatabase,
    user_id: str,
    *,
    semester_codes: list[str],
    candidates: list[dict[str, Any]],
    max_credits: float | None = None,
    current_year: int | None = None,
) -> dict[str, Any]:
    """Build a conflict-free plan for one or more terms from agent-supplied candidates.

    A term may be NAMED ("winter") or CODED ("2025-1"); a bare name resolves to
    `current_year` (today's, unless injected). The label is echoed back on each
    placed course so the caller splits the plan on exactly what it passed."""
    if not semester_codes:
        return {"status": "validation_error", "errors": ["At least one semesterCode is required"]}
    if not candidates:
        return {"status": "validation_error", "errors": ["At least one candidate course is required"]}

    preferred_year = current_year or date.today().year
    term_keys: list[tuple[str, int, int]] = []
    for code in semester_codes:
        resolved = resolve_plan_term(code, preferred_year=preferred_year)
        if resolved is None:
            return {"status": "validation_error", "errors": [f"Invalid semesterCode: {code}"]}
        term_keys.append(resolved)

    context = await load_planning_context(database, user_id)
    if context["status"] != "ok":
        return context

    catalog_courses = context["catalogCourses"]
    courses_by_number = build_courses_by_number(catalog_courses)
    courses_by_id = {
        str(course["_id"]): course for course in catalog_courses if course.get("_id") is not None
    }

    max_credits_limit = _resolve_cap(context["profile"], max_credits)

    completed_records = context["completedCourseRecords"]
    completed_course_ids = set(build_effective_completions(completed_records).keys())
    completed_course_numbers = _completed_numbers(completed_records, courses_by_id)
    overlap_groups = build_catalog_overlap_groups(catalog_courses)

    resolved, unknown = _resolve_candidates(candidates, courses_by_number)
    candidate_numbers = sorted(
        {
            str(candidate.course.get("courseNumber") or candidate.course.get("number") or "")
            for candidate in resolved
        }
    )

    terms: list[TermInput] = []
    for label, academic_year, technion_code in term_keys:
        offerings = await _load_term_offerings(
            database, candidate_numbers, academic_year, technion_code
        )
        terms.append(
            TermInput(
                semester_code=label,
                academic_year=academic_year,
                technion_semester_code=technion_code,
                offerings_by_number=offerings,
            )
        )

    result = plan_terms(
        candidates=resolved,
        terms=terms,
        completed_course_ids=completed_course_ids,
        completed_course_numbers=completed_course_numbers,
        courses_by_number=courses_by_number,
        overlap_groups=overlap_groups,
        max_credits_limit=max_credits_limit,
    )

    result["unscheduled"] = [
        *result["unscheduled"],
        *[{"courseNumber": number, "reason": "Not found in the catalog"} for number in unknown],
    ]
    result["status"] = "ok"
    result["maxCredits"] = max_credits_limit
    return result


def _resolve_cap(profile: dict[str, Any], max_credits: float | None) -> float:
    if max_credits is not None:
        cap = float(max_credits)
    else:
        preferences = profile.get("preferences") or {}
        cap = float(preferences.get("maxCreditsPerSemester") or DEFAULT_MAX_CREDITS)
    return round_credits(min(cap, MAX_CREDITS_CEILING))


def _resolve_candidates(
    candidates: list[dict[str, Any]], courses_by_number: dict[str, dict[str, Any]]
) -> tuple[list[Candidate], list[str]]:
    resolved: list[Candidate] = []
    unknown: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        number = str(item.get("courseNumber") or "").strip()
        if not number or number in seen:
            continue
        seen.add(number)
        category = str(item.get("category") or "elective")
        if category not in VALID_CATEGORIES:
            category = "elective"
        course = courses_by_number.get(number) or courses_by_number.get(
            canonical_course_number(number) or ""
        )
        if not course:
            unknown.append(number)
            continue
        resolved.append(Candidate(course=course, category=category))
    return resolved, unknown


def _completed_numbers(
    completed_records: list[dict[str, Any]], courses_by_id: dict[str, dict[str, Any]]
) -> set[str]:
    """Course NUMBERS of completed courses -- needed for the overlap/coreq rules.

    Completed records key on `courseId`; a number is recovered from the record
    itself when present, else via the catalog. Best-effort: an unrecoverable number
    only weakens overlap/coreq detection, never dedup (which is id-based)."""
    numbers: set[str] = set()
    for record in completed_records:
        number = record.get("courseNumber")
        if number:
            numbers.add(str(number))
            continue
        course = courses_by_id.get(str(record.get("courseId") or ""))
        if course and course.get("courseNumber"):
            numbers.add(str(course["courseNumber"]))
    return numbers


async def _load_term_offerings(
    database: AsyncIOMotorDatabase,
    numbers: list[str],
    academic_year: int,
    technion_semester_code: int,
) -> dict[str, dict[str, Any]]:
    if not numbers:
        return {}
    return await catalog_repository.list_best_offerings_for_courses(
        database,
        numbers,
        academic_year=academic_year,
        semester_code=technion_semester_code,
    )


__all__ = ["build_term_plan"]
