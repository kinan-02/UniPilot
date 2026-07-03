"""Per-intent required context fields (spec §18)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentIntent

ContextRequirementSpec = dict[str, list[str]]

REQUIREMENTS_BY_INTENT: dict[AgentIntent, ContextRequirementSpec] = {
    "graduation_progress_check": {
        "required": [
            "userContext.profile",
            "userContext.completedCourses",
        ],
        "optional": [
            "academicContext.degreeRequirements",
            "retrievedWikiContext",
        ],
    },
    "course_question": {
        "required": [
            "userContext.profile",
            "userContext.completedCourses",
            "entities.courseNumber",
        ],
        "optional": [
            "entities.targetSemesterCode",
            "academicContext.course",
            "academicContext.offering",
            "academicContext.prerequisiteResult",
            "academicContext.requirementContribution",
            "retrievedWikiContext",
        ],
    },
    "prerequisite_check": {
        "required": [
            "userContext.completedCourses",
            "entities.courseNumber",
        ],
        "optional": [
            "userContext.profile",
            "academicContext.course",
            "academicContext.prerequisiteResult",
            "academicContext.requirementContribution",
            "retrievedWikiContext",
        ],
    },
    "semester_plan_generation": {
        "required": [
            "userContext.profile",
            "userContext.completedCourses",
            "entities.targetSemesterCode",
        ],
        "optional": [
            "academicContext.degreeRequirements",
            "userContext.preferences",
            "userContext.semesterPlans",
            "retrievedWikiContext",
        ],
    },
    "requirement_explanation": {
        "required": ["userContext.profile"],
        "optional": [
            "academicContext.degreeRequirements",
            "retrievedWikiContext",
        ],
    },
    "transcript_import": {
        "required": ["userContext.completedCourses"],
        "optional": ["userContext.profile"],
    },
    "general_academic_question": {
        "required": [],
        "optional": ["userContext.profile", "retrievedWikiContext"],
    },
    "unknown_or_unsupported": {
        "required": [],
        "optional": [],
    },
    "semester_plan_modification": {
        "required": ["userContext.profile", "userContext.completedCourses"],
        "optional": ["userContext.semesterPlans"],
    },
    "catalog_search": {
        "required": [],
        "optional": ["academicContext.course", "retrievedWikiContext"],
    },
    "completed_courses_update": {
        "required": ["userContext.completedCourses"],
        "optional": ["userContext.profile"],
    },
    "profile_update": {
        "required": ["userContext.profile"],
        "optional": [],
    },
}


def get_requirements_for_intent(intent: AgentIntent) -> ContextRequirementSpec:
    return REQUIREMENTS_BY_INTENT.get(
        intent,
        {"required": [], "optional": []},
    )


def get_nested_value(root: dict[str, Any], dotted_path: str) -> Any:
    current: Any = root
    for part in dotted_path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, set, tuple)):
        return len(value) > 0
    return True


def is_required_field_satisfied(root: dict[str, Any], dotted_path: str) -> bool:
    """Return whether a required context field is present (empty collections may be valid)."""
    value = get_nested_value(root, dotted_path)
    if dotted_path == "userContext.completedCourses":
        return isinstance(value, list)
    return is_present(value)
