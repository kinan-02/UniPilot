"""Deterministic helpers for the Planner agent (graph ground truth)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.api_catalog import (
    course_is_api_validated,
    is_course_in_active_catalog,
    uses_api_semester_catalog,
)
from app.services.graph_tools import _retrieve_graph_data
from app.services.semester_catalog import (
    SemesterCatalogInfo,
    discover_semester_catalogs,
    resolve_semester_from_query,
)

COURSE_CODE_RE = re.compile(r"\d{8}")
SEMESTER_FILE_RE = re.compile(r"courses_(\d{4})_(200|201|202)\.json", re.IGNORECASE)


def extract_course_codes(goal: str) -> list[str]:
    return list(dict.fromkeys(COURSE_CODE_RE.findall(goal)))


def extract_explicit_semester_filename(goal: str) -> str | None:
    match = SEMESTER_FILE_RE.search(goal)
    if not match:
        return None
    return f"courses_{match.group(1)}_{match.group(2)}.json"


def resolve_semester_for_goal(
    goal: str,
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    *,
    profile_plan_semester_code: str | None = None,
) -> tuple[SemesterCatalogInfo | None, list[str]]:
    """Pick and activate a semester catalog from goal text when possible."""
    references: list[str] = []
    catalogs = discover_semester_catalogs(Path(technion_raw_dir))
    if not catalogs:
        active = engine.active_semester
        return active, references

    explicit = extract_explicit_semester_filename(goal)

    resolution = resolve_semester_from_query(
        goal,
        catalogs,
        explicit_filename=explicit,
    )
    if (
        explicit is None
        and profile_plan_semester_code
        and resolution.get("needs_clarification")
    ):
        profile_resolution = resolve_semester_from_query(
            goal,
            catalogs,
            explicit_plan_code=str(profile_plan_semester_code).strip(),
        )
        profile_semester = profile_resolution.get("semester")
        if isinstance(profile_semester, SemesterCatalogInfo):
            resolution = profile_resolution
            references.append(f"semester:profile_plan_code={profile_plan_semester_code}")

    semester = resolution.get("semester")
    if isinstance(semester, SemesterCatalogInfo):
        if engine.active_semester is None or engine.active_semester.filename != semester.filename:
            engine.set_active_semester(semester.filename, technion_raw_dir)
            engine.build_graph()
        references.append(f"semester:{semester.filename}")
        references.append(f"semester_resolve:confidence={resolution.get('confidence')}")
        assumption = resolution.get("assumption_note")
        if isinstance(assumption, str) and assumption.strip():
            references.append(f"semester_resolve:assumption={assumption.strip()}")
        return semester, references

    return engine.active_semester, references


def eligibility_tool_refs(
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    course_id: str,
    completed_courses: list[str],
    semester_filename: str | None = None,
) -> tuple[bool, list[str]]:
    """Run eligibility retrieval and return eligibility plus citation refs."""
    payload = _retrieve_graph_data(
        engine,
        technion_raw_dir,
        completed_courses,
        "eligibility",
        course_id=course_id,
        semester_filename=semester_filename,
    )
    eligible, missing = engine.evaluate_eligibility(course_id, completed_courses)
    references = [
        f"eligibility:{course_id}:eligible={eligible}",
        f"tool:retrieve_graph_data:eligibility:{course_id}",
    ]
    if missing:
        references.append(f"missing_prerequisites:{course_id}:{','.join(missing)}")
    if "error" in payload:
        references.append(f"tool_error:eligibility:{course_id}")
    return eligible, references


def filter_eligible_courses(
    *,
    engine: AcademicGraphEngine,
    technion_raw_dir: str,
    course_ids: list[str],
    completed_courses: list[str],
    semester_filename: str | None = None,
    user_context: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Keep only active-semester catalog courses the student is eligible to take."""
    eligible_ids: list[str] = []
    references: list[str] = []
    api_catalog = uses_api_semester_catalog(user_context)
    if api_catalog:
        references.append("catalog:source=api_mongo")

    for course_id in course_ids:
        if not is_course_in_active_catalog(
            engine=engine,
            course_id=course_id,
            user_context=user_context,
        ):
            references.append(f"catalog:missing:{course_id}")
            continue
        eligible, course_refs = eligibility_tool_refs(
            engine,
            technion_raw_dir,
            course_id,
            completed_courses,
            semester_filename=semester_filename,
        )
        references.extend(course_refs)
        if api_catalog and course_is_api_validated(course_id, user_context):
            eligible_ids.append(course_id)
            references.append(f"eligibility:{course_id}:api_validated")
            continue
        if eligible:
            eligible_ids.append(course_id)

    return eligible_ids, references


def list_eligible_catalog_courses(
    engine: AcademicGraphEngine,
    completed_courses: list[str],
    *,
    limit: int = 50,
    user_context: dict[str, Any] | None = None,
) -> list[str]:
    if user_context:
        from app.services.path_relevant_planner import list_path_relevant_eligible_courses

        ranked, _references = list_path_relevant_eligible_courses(
            engine,
            completed_courses,
            user_context,
            limit=limit,
        )
        return ranked

    completed = set(completed_courses)
    eligible: list[str] = []
    for course_id in engine.course_catalog.keys():
        if course_id in completed:
            continue
        ok, _missing = engine.evaluate_eligibility(course_id, completed_courses)
        if ok:
            eligible.append(course_id)
        if len(eligible) >= limit:
            break
    return eligible


def parse_course_credits(
    engine: AcademicGraphEngine,
    course_id: str,
    user_context: dict[str, Any] | None = None,
) -> float:
    if user_context:
        from app.services.api_catalog import api_course_credits_map

        api_credits = api_course_credits_map(user_context).get(course_id)
        if api_credits is not None:
            return api_credits

    if not engine._built:
        return 0.0
    node = engine.graph.nodes.get(course_id, {})
    raw = node.get("credits", "")
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw or "").strip().replace(",", ".")
    if not text:
        entry = engine.course_catalog.get(course_id, {})
        general = entry.get("general", {})
        text = str(general.get("נקודות", "") or "").strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return 0.0


def sum_plan_credits(
    engine: AcademicGraphEngine,
    course_ids: list[str],
    user_context: dict[str, Any] | None = None,
) -> float:
    return round(
        sum(parse_course_credits(engine, course_id, user_context=user_context) for course_id in course_ids),
        2,
    )
