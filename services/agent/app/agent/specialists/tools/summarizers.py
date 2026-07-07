"""Deterministic, bounded summarizers for specialist tool observations (Phase 12).

Every summarizer takes an already-extracted raw fragment (see
`adapters.py`) and shapes it into a small, capped, JSON-safe `dict` --
never a full structured document, never an unbounded list, never a raw
Mongo document. Safety filtering (`safety.py`) is applied by the caller
(`observation_builder.py`) afterwards, defense-in-depth; these functions
still deliberately hand-pick only a narrow, known-safe set of fields
instead of passing a raw fragment through unchanged.

Pure functions only -- no I/O, no LLM calls, never raise on a malformed
fragment (missing/wrong-typed keys are simply omitted).
"""

from __future__ import annotations

from typing import Any

_SNIPPET_PREVIEW_MAX_LENGTH = 220
_ASSUMPTION_PREVIEW_MAX_LENGTH = 200

_PROFILE_KEYS = ("degreeId", "degreeProgram", "track", "catalogYear", "facultyId", "currentSemesterCode")
_GRADUATION_AUDIT_KEYS = (
    "creditsEarned",
    "creditsRequired",
    "creditsRemaining",
    "isEligibleForGraduation",
    "status",
)
_REQUIREMENT_BUCKET_KEYS = ("id", "requirementGroupId", "name", "category", "minCredits", "creditsRequired", "ruleType")
_COURSE_CATALOG_KEYS = ("id", "courseNumber", "title", "credits", "facultyId")
_PREREQUISITE_KEYS = ("eligible", "missingPrerequisiteIds", "satisfiedPrerequisiteIds")
_OFFERING_KEYS = ("courseNumber", "academicYear", "semesterCode", "seatsAvailable", "instructor")
_REQUIREMENT_CONTRIBUTION_KEYS = ("category", "bucketName", "satisfies", "contributionType")


def _preview(text: str, *, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "…"


def _pick(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def summarize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return _pick(profile, _PROFILE_KEYS)


def summarize_completed_courses(fields: dict[str, Any], *, max_items: int) -> dict[str, Any]:
    numbers = fields.get("completedCourses") or []
    records = fields.get("completedCourseRecords") or []
    ids = fields.get("completedCourseIds") or []
    count = len(numbers) or len(records) or len(ids)
    return {
        "completedCourseCount": count,
        "sampleCourseNumbers": [str(item) for item in list(numbers)[: max(0, max_items)]],
        "dataQuality": fields.get("dataQuality") or {},
    }


def summarize_graduation_audit(audit: dict[str, Any], *, max_items: int) -> dict[str, Any]:
    summary = _pick(audit, _GRADUATION_AUDIT_KEYS)
    missing = audit.get("missingRequirements")
    if isinstance(missing, list):
        summary["missingRequirementCount"] = len(missing)
        summary["sampleMissingRequirements"] = [str(item) for item in missing[: max(0, max_items)]]
    return summary


def summarize_requirement_buckets(buckets: list[dict[str, Any]], *, max_items: int) -> dict[str, Any]:
    capped = max(0, max_items)
    sample = [entry for item in buckets[:capped] if (entry := _pick(item, _REQUIREMENT_BUCKET_KEYS))]
    return {"bucketCount": len(buckets), "sampleBuckets": sample}


def summarize_course_catalog(course: dict[str, Any]) -> dict[str, Any]:
    return _pick(course, _COURSE_CATALOG_KEYS)


def summarize_prerequisites(result: dict[str, Any]) -> dict[str, Any]:
    summary = _pick(result, _PREREQUISITE_KEYS)
    missing = summary.get("missingPrerequisiteIds")
    if isinstance(missing, list):
        summary["missingPrerequisiteCount"] = len(missing)
    return summary


def summarize_offering(fields: dict[str, Any], *, max_items: int) -> dict[str, Any]:
    offering = fields.get("offering") if isinstance(fields.get("offering"), dict) else {}
    offerings = fields.get("offerings") if isinstance(fields.get("offerings"), list) else []
    return {
        "offeringFound": bool(offering),
        "offeringCount": min(len(offerings), max(0, max_items)) if offerings else (1 if offering else 0),
        "primaryOffering": _pick(offering, _OFFERING_KEYS) if offering else {},
    }


def summarize_requirement_contribution(contribution: Any) -> dict[str, Any]:
    if isinstance(contribution, dict):
        return _pick(contribution, _REQUIREMENT_CONTRIBUTION_KEYS)
    if isinstance(contribution, list):
        return {"contributionCount": len(contribution)}
    return {"contributionPreview": _preview(str(contribution), max_length=_ASSUMPTION_PREVIEW_MAX_LENGTH)}


def summarize_wiki_snippets(snippets: list[Any], *, max_items: int) -> dict[str, Any]:
    capped = max(0, max_items)
    sample: list[dict[str, Any]] = []
    for snippet in snippets[:capped]:
        if isinstance(snippet, dict):
            page_title = snippet.get("page_title") or snippet.get("pageTitle")
            section_title = snippet.get("section_title") or snippet.get("sectionTitle")
            content = snippet.get("content") or ""
            score = snippet.get("score")
        else:
            page_title = getattr(snippet, "page_title", None)
            section_title = getattr(snippet, "section_title", None)
            content = getattr(snippet, "content", "") or ""
            score = getattr(snippet, "score", None)
        sample.append(
            {
                "pageTitle": page_title,
                "sectionTitle": section_title,
                "preview": _preview(str(content), max_length=_SNIPPET_PREVIEW_MAX_LENGTH),
                "score": score,
            }
        )
    return {"snippetCount": len(snippets), "sampleSnippets": sample}


def summarize_conversation_assumptions(assumptions: list[str], *, max_items: int) -> dict[str, Any]:
    capped = max(0, max_items)
    return {
        "assumptionCount": len(assumptions),
        "sampleAssumptions": [
            _preview(str(item), max_length=_ASSUMPTION_PREVIEW_MAX_LENGTH) for item in assumptions[:capped]
        ],
    }


__all__ = [
    "summarize_completed_courses",
    "summarize_conversation_assumptions",
    "summarize_course_catalog",
    "summarize_graduation_audit",
    "summarize_offering",
    "summarize_prerequisites",
    "summarize_profile",
    "summarize_requirement_buckets",
    "summarize_requirement_contribution",
    "summarize_wiki_snippets",
]
