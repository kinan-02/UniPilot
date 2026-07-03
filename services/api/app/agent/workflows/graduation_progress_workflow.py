"""Graduation progress workflow — deterministic audit (spec §30.1)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.graduation_response_builder import (
    build_graduation_response_blocks,
    build_graduation_summary_text,
    build_suggested_followups,
)
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent, StructuredBlock
from app.services.graduation_audit_service import GraduationAuditResult, run_graduation_audit
from app.services.requirement_matching_service import match_degree_requirements


class GraduationProgressWorkflow:
    name = "graduation_progress_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        yield StreamEvent(
            type="agent.step.started",
            label="Matching degree requirements",
            run_id=context.run_id,
        )

        audit = await run_graduation_audit(database, user_id=context.user_id, context=context)
        matching = match_degree_requirements(
            progress=audit.progress or {},
            catalog_requirements=context.academic_context.get("degreeRequirements"),
        )

        yield StreamEvent(
            type="agent.step.completed",
            label="Matching degree requirements",
            run_id=context.run_id,
        )

        if audit.status != "ok" or not audit.progress:
            text, warnings = _failure_response(audit, context)
            yield AgentResponse(
                conversation_id=context.conversation_id,
                message_id="",
                run_id=context.run_id,
                text=text,
                warnings=warnings,
                blocks=[_source_summary_block(context)],
                suggested_prompts=[
                    "Update my student profile",
                    "Import my transcript",
                ],
                assumptions=list(context.missing_data),
                used_sources=_used_sources(context),
            )
            return

        yield StreamEvent(
            type="agent.step.started",
            label="Checking graduation progress",
            run_id=context.run_id,
        )

        blocks = build_graduation_response_blocks(audit=audit, matching=matching, context=context)
        summary = build_graduation_summary_text(audit=audit, matching=matching, context=context)

        yield StreamEvent(
            type="agent.step.completed",
            label="Checking graduation progress",
            run_id=context.run_id,
        )

        for block in blocks:
            yield StreamEvent(type="structured_output", block=block, run_id=context.run_id)

        yield compose_response(
            conversation_id=context.conversation_id,
            message_id="",
            run_id=context.run_id,
            text=summary,
            blocks=blocks,
            warnings=list({*audit.warnings, *context.validation.warnings}),
            suggested_prompts=build_suggested_followups(audit=audit),
            assumptions=list(audit.assumptions),
            used_sources=_used_sources(context),
        )


def _failure_response(audit: GraduationAuditResult, context: AgentContextPack) -> tuple[str, list[str]]:
    warnings = list({*audit.warnings, *context.validation.warnings, *audit.errors})
    if audit.status == "profile_not_found":
        return (
            "I could not find your student profile. Please complete your profile before checking graduation progress.",
            warnings,
        )
    if audit.status == "degree_not_selected":
        return (
            "Please select your degree program and track on your profile so I can calculate graduation progress.",
            warnings,
        )
    if audit.status == "degree_not_found":
        return (
            "Your profile references a degree that is not in the catalog. Please update your degree selection.",
            warnings,
        )
    return ("I could not calculate graduation progress right now.", warnings)


def _source_summary_block(context: AgentContextPack) -> StructuredBlock:
    return StructuredBlock(
        type="SourceSummaryBlock",
        data={
            "provenance": context.provenance,
            "wikiSnippetCount": len(context.retrieved_wiki_context),
            "validationStatus": context.validation.status,
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
