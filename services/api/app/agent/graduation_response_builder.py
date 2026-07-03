"""Build structured graduation UI blocks for the agent (spec §30.1 + Agent_UI_UX.md)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentContextPack, StructuredBlock, WikiContextSnippet
from app.services.graduation_audit_service import GraduationAuditResult
from app.services.requirement_matching_service import RequirementMatchingSummary

_GRADUATION_STATUS_LABELS = {
    "ready_to_graduate": "Ready for graduation",
    "not_ready": "Not ready yet",
    "needs_review": "Needs review",
    "missing_data": "Missing data",
}


def build_graduation_response_blocks(
    *,
    audit: GraduationAuditResult,
    matching: RequirementMatchingSummary,
    context: AgentContextPack,
) -> list[StructuredBlock]:
    progress = audit.progress or {}
    blocks: list[StructuredBlock] = [
        _requirement_summary_block(audit=audit, progress=progress, matching=matching),
    ]

    for entry in matching.entries:
        bucket_source = _find_bucket_in_progress(progress, entry.requirement_group_id)
        blocks.append(_requirement_bucket_block(entry=entry, bucket=bucket_source, context=context))

    for warning in audit.warnings[:6]:
        blocks.append(StructuredBlock(type="WarningBlock", data={"message": warning}))

    if audit.blockers:
        blocks.append(
            StructuredBlock(
                type="WarningBlock",
                data={
                    "title": "Main blockers",
                    "messages": audit.blockers,
                },
            )
        )

    blocks.append(_source_summary_block(audit=audit, context=context, matching=matching))
    return blocks


def build_graduation_summary_text(
    *,
    audit: GraduationAuditResult,
    matching: RequirementMatchingSummary,
    context: AgentContextPack,
) -> str:
    if audit.status != "ok" or not audit.progress:
        return ""

    progress = audit.progress
    profile = (context.user_context.get("profile") or {}) if context.user_context else {}
    degree_name = progress.get("degreeName") or profile.get("degreeProgram") or "your degree"
    status_label = _GRADUATION_STATUS_LABELS.get(audit.graduation_status, audit.graduation_status)

    parts = [
        f"Here is your graduation progress for {degree_name}.",
        f"Status: {status_label}.",
    ]

    completed = progress.get("completedCredits")
    required = progress.get("totalRequiredCredits")
    if completed is not None and required is not None:
        parts.append(f"You have completed {completed} of {required} credits.")

    remaining = progress.get("creditsRemaining")
    if remaining is not None:
        parts.append(f"About {remaining} credits remain toward the degree total.")

    completion = progress.get("completionPercentage")
    if completion is not None:
        parts.append(f"Overall completion is approximately {completion}%.")

    parts.append(
        f"{matching.satisfied_count} of {matching.total_requirements} requirement buckets are fully satisfied."
    )

    if audit.blockers:
        parts.append(f"Main blocker: {audit.blockers[0]}")

    return " ".join(parts)


def build_suggested_followups(*, audit: GraduationAuditResult) -> list[str]:
    if audit.graduation_status == "ready_to_graduate":
        return [
            "What paperwork do I need to graduate?",
            "Build a final-semester plan",
        ]
    return [
        "What courses should I take next semester?",
        "Explain my remaining requirements",
        "Which mandatory courses am I still missing?",
    ]


def _requirement_summary_block(
    *,
    audit: GraduationAuditResult,
    progress: dict[str, Any],
    matching: RequirementMatchingSummary,
) -> StructuredBlock:
    return StructuredBlock(
        type="RequirementSummaryBlock",
        data={
            "graduationStatus": audit.graduation_status,
            "graduationStatusLabel": _GRADUATION_STATUS_LABELS.get(
                audit.graduation_status,
                audit.graduation_status,
            ),
            "canGraduate": audit.can_graduate,
            "completionPercentage": progress.get("completionPercentage"),
            "creditsCompleted": progress.get("completedCredits"),
            "creditsRequired": progress.get("totalRequiredCredits"),
            "creditsRemaining": progress.get("creditsRemaining"),
            "transcriptCreditsTotal": progress.get("transcriptCreditsTotal"),
            "degreeAppliedCredits": progress.get("degreeAppliedCredits"),
            "remainingMandatoryCount": len(progress.get("remainingMandatoryCourses") or []),
            "requirementCoveragePercentage": matching.coverage_percentage,
            "satisfiedRequirementCount": matching.satisfied_count,
            "totalRequirementCount": matching.total_requirements,
            "mainBlockers": audit.blockers[:3],
            "degreeCode": progress.get("degreeCode"),
            "degreeName": progress.get("degreeName"),
            "catalogYear": progress.get("catalogYear"),
        },
    )


def _requirement_bucket_block(
    *,
    entry: Any,
    bucket: dict[str, Any] | None,
    context: AgentContextPack,
) -> StructuredBlock:
    bucket = bucket or {}
    wiki_excerpt = _wiki_excerpt_for_bucket(context.retrieved_wiki_context, entry.title)
    return StructuredBlock(
        type="RequirementBucketBlock",
        data={
            "bucketId": entry.requirement_group_id,
            "requirementGroupId": entry.requirement_group_id,
            "label": entry.title,
            "title": entry.title,
            "creditsCompleted": entry.credits_completed,
            "creditsRequired": entry.credits_required,
            "creditsRemaining": entry.credits_remaining,
            "status": _bucket_ui_status(entry.status),
            "rawStatus": entry.status,
            "remainingCourseCount": entry.remaining_course_count,
            "completedCourses": (bucket.get("completedCourses") or [])[:8],
            "remainingCourses": (bucket.get("remainingCourses") or [])[:8],
            "poolConstraints": bucket.get("poolConstraints"),
            "wikiExcerpt": wiki_excerpt,
            "warnings": _bucket_warnings(bucket),
        },
    )


def _bucket_ui_status(raw_status: str) -> str:
    mapping = {
        "satisfied": "completed",
        "in_progress": "partial",
        "partial": "partial",
        "missing": "missing",
        "blocked": "blocked",
    }
    return mapping.get(raw_status, "needs_review")


def _find_bucket_in_progress(progress: dict[str, Any], group_id: str) -> dict[str, Any] | None:
    for entry in progress.get("requirementProgress") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("requirementGroupId") or "") == group_id:
            return entry
    return None


def _bucket_warnings(bucket: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    constraints = bucket.get("poolConstraints") or []
    if isinstance(constraints, list):
        for item in constraints:
            if isinstance(item, dict) and item.get("message"):
                warnings.append(str(item["message"]))
    return warnings


def _wiki_excerpt_for_bucket(
    snippets: list[WikiContextSnippet],
    bucket_title: str | None,
) -> dict[str, Any] | None:
    if not snippets or not bucket_title:
        return None
    title_lower = bucket_title.lower()
    for snippet in snippets:
        haystack = " ".join(
            [
                snippet.section_title or "",
                snippet.page_title or "",
                snippet.content,
            ]
        ).lower()
        if title_lower in haystack or any(token in haystack for token in title_lower.split() if len(token) > 3):
            return {
                "pageTitle": snippet.page_title,
                "sectionTitle": snippet.section_title,
                "sourceFile": snippet.source_file,
                "content": snippet.content[:400],
                "score": snippet.score,
            }
    if snippets:
        first = snippets[0]
        return {
            "pageTitle": first.page_title,
            "sectionTitle": first.section_title,
            "sourceFile": first.source_file,
            "content": first.content[:400],
            "score": first.score,
        }
    return None


def _source_summary_block(
    *,
    audit: GraduationAuditResult,
    context: AgentContextPack,
    matching: RequirementMatchingSummary,
) -> StructuredBlock:
    return StructuredBlock(
        type="SourceSummaryBlock",
        data={
            "provenance": context.provenance,
            "wikiSnippetCount": len(context.retrieved_wiki_context),
            "validationStatus": context.validation.status,
            "assumptions": audit.assumptions,
            "unmatchedCatalogRules": matching.unmatched_catalog_rules,
            "usedSources": _used_sources(context),
        },
    )


def _used_sources(context: AgentContextPack) -> list[str]:
    if context.provenance:
        return list(context.provenance)
    return [
        "mongodb:student_profile",
        "mongodb:completed_courses",
        "catalog:degree_requirements",
    ]
