"""Data-quality signals for MAS user context loading."""

from __future__ import annotations

from typing import Any

from app.services.plan_progress import _normalize_course_number

MAX_COMPLETED_RECORDS = 10_000

WARNING_MESSAGES: dict[str, str] = {
    "transcript_truncated": "Transcript was truncated at the load limit; some completions may be missing.",
    "transcript_unresolved": "Completed courses exist but none could be matched to the catalog.",
    "transcript_partial_resolution": "Some completed courses could not be matched to catalog entries.",
    "no_transcript_records": "No completed courses were found on your transcript.",
    "profile_not_found": "Student profile was not found.",
    "degree_not_selected": "No degree program is selected on your profile.",
    "track_not_set": "Academic track is not set on your profile.",
    "graduation_unavailable": "Graduation progress could not be loaded; path-aware planning is limited.",
    "degree_not_found": "The selected degree program was not found in the catalog.",
}


def normalize_completed_course_numbers(numbers: list[str]) -> list[str]:
    """Return sorted unique 8-digit course numbers for graph eligibility checks."""
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in numbers:
        value = _normalize_course_number(str(raw))
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return sorted(normalized)


def build_transcript_quality_warnings(
    *,
    completed_record_count: int,
    resolved_completed_count: int,
    unresolved_course_count: int,
    truncated: bool,
) -> list[str]:
    warnings: list[str] = []
    if truncated:
        warnings.append("transcript_truncated")
    if completed_record_count == 0:
        warnings.append("no_transcript_records")
    elif resolved_completed_count == 0:
        warnings.append("transcript_unresolved")
    elif unresolved_course_count > 0:
        warnings.append("transcript_partial_resolution")
    return warnings


def build_profile_quality_warnings(
    profile: dict[str, Any] | None,
    *,
    track_slug: str | None = None,
) -> list[str]:
    if not profile:
        return ["profile_not_found"]
    warnings: list[str] = []
    if not profile.get("degreeId"):
        warnings.append("degree_not_selected")
    if not (isinstance(track_slug, str) and track_slug.strip()):
        warnings.append("track_not_set")
    return warnings


def merge_data_quality(*warning_lists: list[str]) -> dict[str, Any]:
    warnings = sorted({warning for group in warning_lists for warning in group})
    return {"warnings": warnings, "ok": len(warnings) == 0}


def append_data_quality_warning(user_context: dict[str, Any], warning: str) -> dict[str, Any]:
    existing = user_context.get("data_quality")
    warnings = list(existing.get("warnings") or []) if isinstance(existing, dict) else []
    if warning not in warnings:
        warnings.append(warning)
    return {
        **user_context,
        "data_quality": {"warnings": sorted(warnings), "ok": len(warnings) == 0},
    }
