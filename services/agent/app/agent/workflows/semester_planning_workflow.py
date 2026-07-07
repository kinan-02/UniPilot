"""Semester planning workflow (spec §30.4)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.llm_preference_extractor import extract_planning_preferences
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, ProposedAction, StreamEvent, StructuredBlock
from app.agent.semester_planning_response_builder import (
    build_semester_planning_blocks,
    build_semester_planning_followups,
    build_semester_planning_text,
)
from app.repositories.agent_action_proposal_repository import create_agent_action_proposal
from app.services.agent_action_helpers import proposal_to_agent_action
from app.services.semester_planning_client import (
    SemesterPlanningResult,
    generate_semester_plan_options,
)


class SemesterPlanningWorkflow:
    name = "semester_planning_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        yield StreamEvent(
            type="agent.step.started",
            label="Checking missing requirements",
            run_id=context.run_id,
        )
        yield StreamEvent(
            type="agent.step.completed",
            label="Checking missing requirements",
            run_id=context.run_id,
        )

        yield StreamEvent(
            type="agent.step.started",
            label="Building schedule options",
            run_id=context.run_id,
        )

        merged_entities = await extract_planning_preferences(
            user_message,
            existing_entities=context.entities,
        )
        context = context.model_copy(update={"entities": merged_entities})

        result = await generate_semester_plan_options(
            user_id=context.user_id,
            context=context,
        )

        yield StreamEvent(
            type="agent.step.completed",
            label="Building schedule options",
            run_id=context.run_id,
        )

        if result.status != "ok":
            text, blocks, warnings = _failure_response(result, context)
            yield compose_response(
                conversation_id=context.conversation_id,
                message_id="",
                run_id=context.run_id,
                text=text,
                blocks=blocks,
                warnings=warnings,
                suggested_prompts=[
                    "Update my student profile",
                    "What am I missing to graduate?",
                ],
                assumptions=list(result.assumptions),
                used_sources=list(context.provenance),
            )
            return

        proposed_actions = await _create_save_plan_proposals(
            database,
            context=context,
            result=result,
        )
        blocks = build_semester_planning_blocks(
            context=context,
            result=result,
            proposed_actions=proposed_actions,
        )
        summary = build_semester_planning_text(result=result)

        for block in blocks:
            yield StreamEvent(type="structured_output", block=block, run_id=context.run_id)

        for action in proposed_actions:
            yield StreamEvent(type="action.proposed", action=action, run_id=context.run_id)

        yield compose_response(
            conversation_id=context.conversation_id,
            message_id="",
            run_id=context.run_id,
            text=summary,
            blocks=blocks,
            warnings=list({*result.warnings, *context.validation.warnings}),
            suggested_prompts=build_semester_planning_followups(result=result),
            proposed_actions=proposed_actions,
            assumptions=list(result.assumptions),
            used_sources=list(context.provenance),
        )


async def _create_save_plan_proposals(
    database: AsyncIOMotorDatabase,
    *,
    context: AgentContextPack,
    result: SemesterPlanningResult,
) -> list[ProposedAction]:
    actions: list[ProposedAction] = []
    for option in result.options:
        proposal = await create_agent_action_proposal(
            database,
            conversation_id=context.conversation_id,
            user_id=context.user_id,
            run_id=context.run_id,
            action_type="save_semester_plan",
            title=f"Save option {option.optionId} — {option.label}",
            description=option.description,
            payload={
                "optionId": option.optionId,
                "semesterCode": option.semesterCode,
                "label": option.label,
                "totalCredits": option.totalCredits,
                "plannedCourses": option.plannedCourses,
                "scheduleSelections": option.scheduleSelections,
                "description": option.description,
            },
            preview=option.model_dump(),
        )
        actions.append(ProposedAction(**proposal_to_agent_action(proposal)))
    return actions


def _failure_response(
    result: SemesterPlanningResult,
    context: AgentContextPack,
) -> tuple[str, list[StructuredBlock], list[str]]:
    warnings = list({*result.warnings, *context.validation.warnings, *result.errors})
    if result.status == "profile_not_found":
        return (
            "I need your student profile before I can build a semester plan.",
            [_warning_block(warnings)],
            warnings,
        )
    if result.status == "validation_error" and any(
        "semester" in error.lower() for error in result.errors
    ):
        return (
            "Which semester should I plan for? Say 'next semester' or provide a semester code like 2025-2.",
            [_warning_block(warnings)],
            warnings,
        )
    if result.status == "no_options":
        return (
            "I could not find viable courses for that semester. Try another semester or update your profile.",
            [_warning_block(warnings)],
            warnings,
        )
    message = result.errors[0] if result.errors else "I could not generate semester plan options."
    return message, [_warning_block(warnings)], warnings


def _warning_block(warnings: list[str]) -> StructuredBlock:
    return StructuredBlock(type="WarningBlock", data={"messages": warnings})
