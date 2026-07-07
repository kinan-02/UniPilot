"""Validate AgentContextPack against workflow requirements (spec §18)."""

from __future__ import annotations

from typing import Any, Literal

from app.agent.schemas import AgentContextPack, ContextValidation, WikiContextSnippet
from app.retrieval.provenance import ProvenanceRecord
from app.validation.context_requirements import (
    get_nested_value,
    get_requirements_for_intent,
    is_present,
    is_required_field_satisfied,
)
from app.retrieval.profiles import get_profile, profile_allows_wiki

ValidationStatus = Literal[
    "valid",
    "valid_with_warnings",
    "needs_more_context",
    "needs_user_clarification",
    "failed",
    "invalid",
    "partial",
]


def _pack_as_dict(pack: AgentContextPack) -> dict[str, Any]:
    return {
        "userContext": pack.user_context,
        "academicContext": pack.academic_context,
        "entities": pack.entities,
        "retrievedWikiContext": [
            snippet.model_dump() if isinstance(snippet, WikiContextSnippet) else snippet
            for snippet in pack.retrieved_wiki_context
        ],
        "missingData": pack.missing_data,
        "warnings": pack.warnings,
    }


def validate_context_pack(pack: AgentContextPack) -> ContextValidation:
    spec = get_requirements_for_intent(pack.intent)
    root = _pack_as_dict(pack)
    errors: list[str] = []
    warnings: list[str] = list(pack.warnings)

    for path in spec.get("required", []):
        if not is_required_field_satisfied(root, path):
            errors.append(f"Missing required context: {path}")

    profile = pack.user_context.get("profile")
    if profile is None and pack.intent in {
        "graduation_progress_check",
        "course_question",
        "semester_plan_generation",
    }:
        errors.append("Student profile is required for this request")

    data_quality = pack.user_context.get("dataQuality") or {}
    for warning in data_quality.get("warnings") or []:
        if warning not in warnings:
            warnings.append(str(warning))

    if pack.intent in {"course_question", "prerequisite_check"} and not pack.entities.get("courseNumber"):
        errors.append("Course number could not be resolved from the message")

    if pack.intent in {"course_question", "prerequisite_check"} and pack.academic_context.get("course") is None:
        if pack.entities.get("courseNumber"):
            warnings.append(f"Course {pack.entities['courseNumber']} was not found in the catalog")

    if pack.intent == "transcript_import" and not _has_transcript_attachment(pack):
        errors.append("Transcript PDF upload is required for import")

    if pack.intent in {"semester_plan_generation", "semester_plan_modification"}:
        if not pack.entities.get("targetSemesterCode"):
            errors.append("Target semester could not be resolved for planning")

    wiki_meta = pack.retrieval_metadata or {}
    if wiki_meta.get("fallbackUsed"):
        warnings.append("wiki_metadata_filter_relaxed")

    if pack.intent in {"requirement_explanation", "graduation_progress_check"}:
        if not pack.retrieved_wiki_context and not pack.academic_context.get("degreeRequirements"):
            warnings.append("requirement_explanation_context_thin")

    if pack.retrieval_profile:
        profile = get_profile(pack.retrieval_profile)
        top_score = float(wiki_meta.get("topScore") or 0)
        if (
            profile_allows_wiki(profile)
            and pack.retrieved_wiki_context
            and top_score < profile.minRetrievalConfidence
        ):
            warnings.append("low_wiki_retrieval_confidence")

    if not pack.retrieved_wiki_context and pack.intent == "requirement_explanation":
        warnings.append("No catalog wiki sections were retrieved for this explanation")

    status: ValidationStatus
    if errors:
        if any("profile" in error.lower() for error in errors):
            status = "needs_user_clarification"
        elif any("course number" in error.lower() for error in errors):
            status = "needs_user_clarification"
        else:
            status = "needs_more_context"
    elif warnings:
        status = "valid_with_warnings"
    else:
        status = "valid"

    # Keep ContextValidation compatible with existing schema while exposing richer status.
    mapped_status: Literal["valid", "invalid", "partial"] = "valid"
    if status in {"failed", "invalid"}:
        mapped_status = "invalid"
    elif status in {"needs_more_context", "needs_user_clarification", "valid_with_warnings"}:
        mapped_status = "partial"

    return ContextValidation(status=mapped_status, errors=errors, warnings=warnings)


def _has_transcript_attachment(pack: AgentContextPack) -> bool:
    for attachment in pack.message_attachments:
        if attachment.get("type") == "transcript_pdf" and isinstance(attachment.get("parsePreview"), dict):
            return True
    return False
