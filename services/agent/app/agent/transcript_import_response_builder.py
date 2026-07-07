"""Structured blocks for transcript import review (Agent_UI_UX.md §20)."""

from __future__ import annotations

from typing import Any

from app.agent.schemas import AgentContextPack, ProposedAction, StructuredBlock
from app.services.transcript_review_service import TranscriptReviewResult


def build_transcript_review_blocks(
    *,
    context: AgentContextPack,
    review: TranscriptReviewResult,
    proposed_action: ProposedAction,
) -> list[StructuredBlock]:
    importable_count = sum(1 for row in review.rows if row.selected and row.status != "duplicate")
    blocks: list[StructuredBlock] = [
        StructuredBlock(
            type="TranscriptReviewBlock",
            data={
                "rows": [row.model_dump() for row in review.rows],
                "totalExtractedCredits": review.totalExtractedCredits,
                "importableCredits": review.importableCredits,
                "matchedCount": review.matchedCount,
                "duplicateCount": review.duplicateCount,
                "uncertainCount": review.uncertainCount,
                "unmatchedCount": review.unmatchedCount,
                "studentId": review.studentId,
                "studentName": review.studentName,
                "parseMetadata": review.parseMetadata,
            },
        ),
        StructuredBlock(
            type="ConfirmationBlock",
            data={
                "title": "Confirm transcript import",
                "description": (
                    f"Import {importable_count} course(s) "
                    f"({review.importableCredits:g} credits). "
                    "Duplicates and unmatched rows will be skipped."
                ),
                "actionId": proposed_action.id,
                "actionType": proposed_action.action_type,
                "confirmLabel": "Import selected courses",
                "cancelLabel": "Cancel",
                "requiresConfirmation": True,
                "summary": {
                    "coursesToImport": importable_count,
                    "duplicatesSkipped": review.duplicateCount,
                    "uncertainRows": review.uncertainCount,
                    "unmatchedRows": review.unmatchedCount,
                },
            },
        ),
        _source_summary_block(context=context, review=review),
    ]

    for warning in review.warnings[:4]:
        blocks.append(StructuredBlock(type="WarningBlock", data={"message": warning}))

    return blocks


def build_transcript_review_text(*, review: TranscriptReviewResult) -> str:
    importable = sum(1 for row in review.rows if row.selected and row.status != "duplicate")
    if importable == 0:
        return (
            "I parsed your transcript but found no new courses ready to import. "
            "Review duplicates, uncertain rows, and unmatched courses below."
        )
    parts = [
        f"I parsed {len(review.rows)} course row(s) from your transcript.",
        f"{importable} course(s) are ready to import after you confirm.",
    ]
    if review.duplicateCount:
        parts.append(f"{review.duplicateCount} duplicate(s) will be skipped.")
    if review.uncertainCount:
        parts.append(f"{review.uncertainCount} row(s) need review because of uncertainty.")
    if review.unmatchedCount:
        parts.append(f"{review.unmatchedCount} row(s) could not be matched to the catalog.")
    parts.append("Nothing will be saved until you confirm the import.")
    return " ".join(parts)


def build_transcript_followups(*, review: TranscriptReviewResult) -> list[str]:
    if review.uncertainCount:
        return [
            "Show only uncertain rows",
            "What am I missing to graduate?",
        ]
    return [
        "What am I missing to graduate?",
        "Import another transcript",
    ]


def build_import_success_text(*, created_count: int, skipped_count: int) -> str:
    parts = [f"Imported {created_count} completed course(s)."]
    if skipped_count:
        parts.append(f"Skipped {skipped_count} duplicate(s).")
    parts.append("You can ask me to recalculate your graduation progress.")
    return " ".join(parts)


def _source_summary_block(
    *,
    context: AgentContextPack,
    review: TranscriptReviewResult,
) -> StructuredBlock:
    return StructuredBlock(
        type="SourceSummaryBlock",
        data={
            "provenance": context.provenance,
            "validationStatus": context.validation.status,
            "parseExtractor": review.parseMetadata.get("extractor"),
            "pipelineVersion": review.parseMetadata.get("pipelineVersion"),
            "usedSources": list(context.provenance) if context.provenance else [
                "transcript_parser:parse",
                "mongodb:completed_courses",
                "catalog:course_lookup",
            ],
        },
    )
