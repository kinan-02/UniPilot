"""Transcript import workflow — parse, review, propose import (spec §30.3)."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, ProposedAction, StreamEvent, StructuredBlock
from app.agent.transcript_import_response_builder import (
    build_transcript_followups,
    build_transcript_review_blocks,
    build_transcript_review_text,
)
from app.repositories.agent_action_proposal_repository import create_agent_action_proposal
from app.services.agent_action_helpers import proposal_to_agent_action
from app.services.transcript_review_service import (
    TranscriptReviewResult,
    build_transcript_review,
    review_rows_for_commit,
)


def _extract_parse_preview(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    for attachment in attachments:
        if attachment.get("type") != "transcript_pdf":
            continue
        preview = attachment.get("parsePreview")
        if isinstance(preview, dict):
            return preview
    return None


class TranscriptImportWorkflow:
    name = "transcript_import_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ):
        parse_preview = _extract_parse_preview(context.message_attachments)
        if parse_preview is None:
            yield AgentResponse(
                conversation_id=context.conversation_id,
                message_id="",
                run_id=context.run_id,
                text=(
                    "Please upload your official Technion transcript PDF. "
                    "I will parse it, match courses to the catalog, and show a review table before saving anything."
                ),
                blocks=[
                    StructuredBlock(
                        type="WarningBlock",
                        data={"message": "transcript_upload_required"},
                    )
                ],
                suggested_prompts=[
                    "Upload transcript PDF",
                    "What am I missing to graduate?",
                ],
                warnings=["transcript_upload_required"],
                used_sources=list(context.provenance),
            )
            return

        yield StreamEvent(
            type="agent.step.started",
            label="Parsing transcript",
            run_id=context.run_id,
        )
        yield StreamEvent(
            type="agent.step.completed",
            label="Parsing transcript",
            run_id=context.run_id,
        )

        yield StreamEvent(
            type="agent.step.started",
            label="Matching courses to catalog",
            run_id=context.run_id,
        )

        review = await build_transcript_review(
            database,
            parse_preview=parse_preview,
            completed_course_records=context.user_context.get("completedCourseRecords") or [],
        )

        yield StreamEvent(
            type="agent.step.completed",
            label="Matching courses to catalog",
            run_id=context.run_id,
        )

        yield StreamEvent(
            type="agent.step.started",
            label="Preparing review table",
            run_id=context.run_id,
        )

        proposal_record = await _create_import_proposal(
            database,
            context=context,
            review=review,
        )
        proposed_action = ProposedAction(**proposal_to_agent_action(proposal_record))
        blocks = build_transcript_review_blocks(
            context=context,
            review=review,
            proposed_action=proposed_action,
        )
        summary = build_transcript_review_text(review=review)

        yield StreamEvent(
            type="agent.step.completed",
            label="Preparing review table",
            run_id=context.run_id,
        )

        for block in blocks:
            yield StreamEvent(type="structured_output", block=block, run_id=context.run_id)

        yield StreamEvent(type="action.proposed", action=proposed_action, run_id=context.run_id)

        yield compose_response(
            conversation_id=context.conversation_id,
            message_id="",
            run_id=context.run_id,
            text=summary,
            blocks=blocks,
            warnings=list(review.warnings),
            suggested_prompts=build_transcript_followups(review=review),
            proposed_actions=[proposed_action],
            assumptions=list(context.missing_data),
            used_sources=list(context.provenance),
        )


async def _create_import_proposal(
    database: AsyncIOMotorDatabase,
    *,
    context: AgentContextPack,
    review: TranscriptReviewResult,
) -> dict[str, Any]:
    commit_rows = review_rows_for_commit(review)
    importable_count = len(commit_rows)
    return await create_agent_action_proposal(
        database,
        conversation_id=context.conversation_id,
        user_id=context.user_id,
        run_id=context.run_id,
        action_type="import_completed_courses",
        title="Import completed courses from transcript",
        description=(
            f"Import {importable_count} selected course(s) from your transcript review. "
            "Duplicates and unmatched rows are excluded."
        ),
        payload={
            "courses": commit_rows,
            "skipDuplicates": True,
            "replaceExisting": False,
        },
        preview={
            "rows": [row.model_dump() for row in review.rows],
            "importableCount": importable_count,
            "totalExtractedCredits": review.totalExtractedCredits,
        },
    )
