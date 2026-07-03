"""Build requirement explanation blocks (spec §30.6)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentContextPack, StructuredBlock, WikiContextSnippet
from app.services.graduation_audit_service import GraduationAuditResult
from app.services.requirement_matching_service import RequirementMatchEntry, RequirementMatchingSummary


def _find_bucket(progress: dict[str, Any], requirement_group_id: str) -> dict[str, Any] | None:
    for entry in progress.get("requirementProgress") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("requirementGroupId") or "") == requirement_group_id:
            return entry
    return None


def _pick_target_entry(
    *,
    matching: RequirementMatchingSummary,
    entities: dict[str, Any],
    user_message: str,
) -> RequirementMatchEntry | None:
    target_id = str(
        entities.get("requirementGroupId")
        or entities.get("requirementBucket")
        or ""
    ).strip()
    if target_id:
        for entry in matching.entries:
            if entry.requirement_group_id == target_id:
                return entry

    lowered = user_message.lower()
    for entry in matching.entries:
        title = (entry.title or "").lower()
        if title and title in lowered:
            return entry

    for entry in matching.entries:
        if entry.status in {"missing", "in_progress", "partial"}:
            return entry

    return matching.entries[0] if matching.entries else None


def build_requirement_explanation_blocks(
    *,
    audit: GraduationAuditResult,
    matching: RequirementMatchingSummary,
    context: AgentContextPack,
    target_entry: RequirementMatchEntry,
) -> list[StructuredBlock]:
    progress = audit.progress or {}
    bucket = _find_bucket(progress, target_entry.requirement_group_id) or {}

    blocks: list[StructuredBlock] = [
        StructuredBlock(
            type="RequirementBucketBlock",
            data={
                "requirementGroupId": target_entry.requirement_group_id,
                "title": target_entry.title or bucket.get("title") or "Requirement",
                "status": target_entry.status,
                "creditsCompleted": target_entry.credits_completed,
                "creditsRequired": target_entry.credits_required,
                "creditsRemaining": target_entry.credits_remaining,
                "remainingCourseCount": target_entry.remaining_course_count,
                "completedCourses": bucket.get("completedCourses") or [],
                "remainingCourses": bucket.get("remainingCourses") or [],
                "eligibleCourses": bucket.get("eligibleCourses") or [],
                "explanationFocus": True,
            },
        )
    ]

    wiki_snippets = context.retrieved_wiki_context[:4]
    if wiki_snippets:
        blocks.append(_wiki_context_block(wiki_snippets))

    for warning in list({*audit.warnings, *context.validation.warnings})[:5]:
        blocks.append(StructuredBlock(type="WarningBlock", data={"message": warning}))

    blocks.append(
        StructuredBlock(
            type="SourceSummaryBlock",
            data={
                "provenance": context.provenance,
                "usedSources": context.provenance[:6],
                "validationStatus": context.validation.status,
            },
        )
    )
    return blocks


def build_requirement_explanation_text(
    *,
    target_entry: RequirementMatchEntry,
    audit: GraduationAuditResult,
    context: AgentContextPack,
) -> str:
    progress = audit.progress or {}
    bucket = _find_bucket(progress, target_entry.requirement_group_id) or {}
    title = target_entry.title or bucket.get("title") or "this requirement"

    parts = [
        f"Here is an explanation of {title}.",
        f"Status: {target_entry.status.replace('_', ' ')}.",
    ]
    if target_entry.credits_required:
        parts.append(
            f"You have {target_entry.credits_completed:g} of "
            f"{target_entry.credits_required:g} required credits in this bucket."
        )
    if target_entry.credits_remaining:
        parts.append(f"About {target_entry.credits_remaining:g} credits remain.")

    remaining = bucket.get("remainingCourses") or []
    if remaining:
        sample = ", ".join(str(item.get("courseNumber") or item) for item in remaining[:4])
        parts.append(f"Example remaining options: {sample}.")

    completed = bucket.get("completedCourses") or []
    if completed:
        parts.append(f"{len(completed)} completed course(s) count toward this bucket.")

    wiki_summary = context.retrieval_metadata.get("wikiExplanationSummary")
    if wiki_summary:
        parts.append("Catalog notes are included in the structured source summary below.")

    return " ".join(parts)


def build_requirement_explanation_followups(*, target_entry: RequirementMatchEntry) -> list[str]:
    return [
        "What am I missing to graduate?",
        f"Which courses satisfy {target_entry.title or 'this requirement'}?",
        "Build a semester plan for next semester",
    ]


def _wiki_context_block(snippets: list[WikiContextSnippet]) -> StructuredBlock:
    return StructuredBlock(
        type="SourceSummaryBlock",
        data={
            "wikiSections": [
                {
                    "title": snippet.page_title or snippet.source_file,
                    "section": snippet.section_title,
                    "preview": (snippet.content or "")[:240],
                }
                for snippet in snippets
            ]
        },
    )
