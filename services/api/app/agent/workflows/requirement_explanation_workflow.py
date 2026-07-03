"""Requirement explanation workflow (spec §30.6)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.requirement_explanation_response_builder import (
    build_requirement_explanation_blocks,
    build_requirement_explanation_followups,
    build_requirement_explanation_text,
)
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent, StructuredBlock
from app.services.graduation_audit_service import GraduationAuditResult, run_graduation_audit
from app.services.requirement_matching_service import match_degree_requirements


class RequirementExplanationWorkflow:
    name = "requirement_explanation_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        yield StreamEvent(
            type="agent.step.started",
            label="Loading graduation audit",
            run_id=context.run_id,
        )

        audit = await run_graduation_audit(database, user_id=context.user_id, context=context)
        matching = match_degree_requirements(
            progress=audit.progress or {},
            catalog_requirements=context.academic_context.get("degreeRequirements"),
        )

        yield StreamEvent(
            type="agent.step.completed",
            label="Loading graduation audit",
            run_id=context.run_id,
        )

        if audit.status != "ok" or not audit.progress:
            text, warnings = _failure_response(audit, context)
            yield compose_response(
                conversation_id=context.conversation_id,
                message_id="",
                run_id=context.run_id,
                text=text,
                blocks=[_warning_block(warnings)],
                warnings=warnings,
                used_sources=list(context.provenance),
            )
            return

        target = _pick_target(matching=matching, context=context, user_message=user_message)
        if target is None:
            yield compose_response(
                conversation_id=context.conversation_id,
                message_id="",
                run_id=context.run_id,
                text=(
                    "I could not identify which requirement bucket you mean. "
                    "Try naming the bucket or asking about a specific missing elective."
                ),
                blocks=[_warning_block(["requirement_bucket_not_identified"])],
                warnings=["requirement_bucket_not_identified"],
                suggested_prompts=["What am I missing to graduate?"],
                used_sources=list(context.provenance),
            )
            return

        yield StreamEvent(
            type="agent.step.started",
            label="Explaining requirement",
            run_id=context.run_id,
        )

        blocks = build_requirement_explanation_blocks(
            audit=audit,
            matching=matching,
            context=context,
            target_entry=target,
        )
        summary = build_requirement_explanation_text(
            target_entry=target,
            audit=audit,
            context=context,
        )

        yield StreamEvent(
            type="agent.step.completed",
            label="Explaining requirement",
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
            suggested_prompts=build_requirement_explanation_followups(target_entry=target),
            assumptions=list(context.assumptions),
            used_sources=list(context.provenance),
        )


def _pick_target(*, matching, context: AgentContextPack, user_message: str):
    from app.agent.requirement_explanation_response_builder import _pick_target_entry

    return _pick_target_entry(
        matching=matching,
        entities=context.entities,
        user_message=user_message,
    )


def _failure_response(audit: GraduationAuditResult, context: AgentContextPack) -> tuple[str, list[str]]:
    warnings = list({*audit.warnings, *context.validation.warnings, *audit.errors})
    if audit.status == "profile_not_found":
        return (
            "Complete your student profile before I can explain specific requirements.",
            warnings,
        )
    return ("I could not load your requirement progress right now.", warnings)


def _warning_block(warnings: list[str]) -> StructuredBlock:
    return StructuredBlock(type="WarningBlock", data={"messages": warnings})
