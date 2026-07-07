"""Deterministic, side-effect-free observation source adapters (Phase 12).

Every function here only ever *reads* from already-available in-memory
data -- an already-built `AgentContextPack` (duck-typed via `Any`, exactly
like `specialists.context.build_agent_context_pack_summary`; never
re-fetched or rebuilt here), a specialist's already-compiled
`compiled_context` dict, or already-computed `dependency_outputs` (other
subtasks' compact output summaries from the supervisor blackboard) --
never a database, an internal API, or an LLM.

Every function returns `None` (or an empty collection) instead of raising
when the expected data isn't present or is shaped unexpectedly -- see
`observation_builder.py`, which treats a `None` result as
`status="missing"`, never a crash.
"""

from __future__ import annotations

from typing import Any


def _get(source: Any, key: str) -> Any:
    if source is None:
        return None
    try:
        if isinstance(source, dict):
            return source.get(key)
        return getattr(source, key, None)
    except Exception:  # noqa: BLE001 -- a hostile/malformed source must never raise here
        return None


def user_context_of(agent_context_pack: Any) -> dict[str, Any]:
    value = _get(agent_context_pack, "user_context")
    return value if isinstance(value, dict) else {}


def academic_context_of(agent_context_pack: Any) -> dict[str, Any]:
    value = _get(agent_context_pack, "academic_context")
    return value if isinstance(value, dict) else {}


def profile_fields(*, agent_context_pack: Any, compiled_context: dict[str, Any]) -> dict[str, Any] | None:
    """Prefer the real, already-built `AgentContextPack.user_context.profile`;
    fall back to the specialist's already-reduced `compiled_context.profile_summary`."""
    profile = user_context_of(agent_context_pack).get("profile")
    if isinstance(profile, dict) and profile:
        return profile
    compiled_profile = compiled_context.get("profile_summary") if isinstance(compiled_context, dict) else None
    if isinstance(compiled_profile, dict) and compiled_profile:
        return compiled_profile
    return None


def completed_courses_fields(*, agent_context_pack: Any) -> dict[str, Any] | None:
    user_context = user_context_of(agent_context_pack)
    numbers = user_context.get("completedCourses")
    records = user_context.get("completedCourseRecords")
    ids = user_context.get("completedCourseIds")
    if not any(isinstance(value, list) and value for value in (numbers, records, ids)):
        return None
    data_quality = user_context.get("dataQuality")
    return {
        "completedCourses": numbers if isinstance(numbers, list) else [],
        "completedCourseRecords": records if isinstance(records, list) else [],
        "completedCourseIds": ids if isinstance(ids, list) else [],
        "dataQuality": data_quality if isinstance(data_quality, dict) else {},
    }


def graduation_audit_fields(
    *, agent_context_pack: Any, dependency_outputs: dict[str, Any]
) -> dict[str, Any] | None:
    """Never calls the graduation-audit internal API itself -- only looks at
    data already present on the (already-built) `AgentContextPack` or in a
    dependency subtask's already-computed output summary."""
    academic = academic_context_of(agent_context_pack)
    audit = academic.get("graduationAudit")
    if isinstance(audit, dict) and audit:
        return audit

    if isinstance(dependency_outputs, dict):
        for value in dependency_outputs.values():
            if not isinstance(value, dict):
                continue
            nested = value.get("graduationAudit")
            if isinstance(nested, dict) and nested:
                return nested
            if {"creditsEarned", "creditsRequired"}.issubset(value.keys()):
                return value
    return None


def requirement_bucket_fields(*, agent_context_pack: Any) -> list[dict[str, Any]] | None:
    academic = academic_context_of(agent_context_pack)
    requirements = academic.get("degreeRequirements")
    if isinstance(requirements, list) and requirements:
        items = [item for item in requirements if isinstance(item, dict)]
        return items or None
    return None


def course_catalog_fields(*, agent_context_pack: Any) -> dict[str, Any] | None:
    academic = academic_context_of(agent_context_pack)
    course = academic.get("course")
    return course if isinstance(course, dict) and course else None


def prerequisite_fields(*, agent_context_pack: Any) -> dict[str, Any] | None:
    academic = academic_context_of(agent_context_pack)
    result = academic.get("prerequisiteResult")
    return result if isinstance(result, dict) and result else None


def offering_fields(*, agent_context_pack: Any) -> dict[str, Any] | None:
    academic = academic_context_of(agent_context_pack)
    offering = academic.get("offering")
    offerings = academic.get("offerings")
    if isinstance(offering, dict) and offering:
        return {
            "offering": offering,
            "offerings": offerings if isinstance(offerings, list) and offerings else [offering],
        }
    if isinstance(offerings, list) and offerings:
        first = offerings[0] if isinstance(offerings[0], dict) else None
        return {"offering": first, "offerings": offerings}
    return None


def requirement_contribution_fields(*, agent_context_pack: Any) -> Any | None:
    academic = academic_context_of(agent_context_pack)
    contribution = academic.get("requirementContribution")
    if contribution in (None, {}, []):
        return None
    return contribution


def wiki_snippet_fields(*, agent_context_pack: Any, compiled_context: dict[str, Any]) -> list[Any]:
    raw = _get(agent_context_pack, "retrieved_wiki_context")
    if isinstance(raw, list) and raw:
        return raw
    compiled_snippets = compiled_context.get("wiki_snippets") if isinstance(compiled_context, dict) else None
    if isinstance(compiled_snippets, list) and compiled_snippets:
        return compiled_snippets
    return []


def conversation_assumption_fields(
    *, agent_context_pack: Any, compiled_context: dict[str, Any]
) -> list[str]:
    assumptions = _get(agent_context_pack, "assumptions")
    if isinstance(assumptions, list) and assumptions:
        return [str(item) for item in assumptions]

    compiled = compiled_context if isinstance(compiled_context, dict) else {}
    pack_summary = compiled.get("agent_context_pack_summary")
    if isinstance(pack_summary, dict):
        summary_assumptions = pack_summary.get("assumptions")
        if isinstance(summary_assumptions, list) and summary_assumptions:
            return [str(item) for item in summary_assumptions]

    conversation_assumptions = compiled.get("conversation_assumptions")
    if isinstance(conversation_assumptions, dict) and conversation_assumptions:
        return [f"{key}={value}" for key, value in conversation_assumptions.items()]
    if isinstance(conversation_assumptions, list) and conversation_assumptions:
        return [str(item) for item in conversation_assumptions]
    return []


__all__ = [
    "academic_context_of",
    "completed_courses_fields",
    "conversation_assumption_fields",
    "course_catalog_fields",
    "graduation_audit_fields",
    "offering_fields",
    "prerequisite_fields",
    "profile_fields",
    "requirement_bucket_fields",
    "requirement_contribution_fields",
    "user_context_of",
    "wiki_snippet_fields",
]
