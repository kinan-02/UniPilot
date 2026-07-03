"""Identify retrieval gaps from a validated context pack (Agent_RAG_tuning.md §26)."""

from __future__ import annotations

from app.agent.schemas import AgentContextPack


def identify_retrieval_gaps(pack: AgentContextPack) -> list[str]:
    gaps: list[str] = []
    warnings = {warning.lower() for warning in pack.validation.warnings}

    if pack.intent in {
        "requirement_explanation",
        "graduation_progress_check",
        "general_academic_question",
    }:
        if not pack.retrieved_wiki_context:
            gaps.append("missing_wiki")
        elif any("thin" in warning for warning in warnings):
            gaps.append("thin_wiki_context")

    if any("low_wiki_retrieval_confidence" in warning for warning in warnings):
        gaps.append("low_wiki_confidence")

    if any("wiki_metadata_filter_relaxed" in warning for warning in warnings):
        gaps.append("metadata_filter_relaxed")

    if pack.intent in {"course_question", "prerequisite_check"}:
        if pack.entities.get("courseNumber") and pack.academic_context.get("course") is None:
            gaps.append("missing_structured_course")

    if pack.intent in {"course_question", "prerequisite_check", "semester_plan_generation"}:
        if pack.entities.get("courseNumber") and pack.entities.get("targetSemesterCode"):
            if pack.academic_context.get("offering") is None:
                gaps.append("missing_offering")

    if pack.validation.errors:
        for error in pack.validation.errors:
            lowered = error.lower()
            if "wiki" in lowered or "catalog" in lowered:
                gaps.append("validation_wiki_gap")
            if "requirement" in lowered:
                gaps.append("validation_requirements_gap")

    deduped: list[str] = []
    seen: set[str] = set()
    for gap in gaps:
        if gap not in seen:
            seen.add(gap)
            deduped.append(gap)
    return deduped
