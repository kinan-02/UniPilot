"""Course question workflow (spec §30.2)."""

from __future__ import annotations

from collections.abc import AsyncIterator

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.course_question_response_builder import (
    build_course_question_blocks,
    build_course_question_followups,
    build_course_question_text,
)
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent
from app.services.course_question_service import analyze_course_question, step_label_for_focus
from app.services.prerequisite_validation_service import ELIGIBILITY_VALIDATION_SOURCE


class CourseQuestionWorkflow:
    name = "course_question_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        analysis = analyze_course_question(context=context, user_message=user_message)
        step_label = step_label_for_focus(analysis.focus)

        yield StreamEvent(
            type="agent.step.started",
            label=step_label,
            run_id=context.run_id,
        )

        provenance = list(context.provenance)
        for source in analysis.catalog_sources:
            label = f"Loaded catalog wiki page [{source}]"
            if label not in provenance:
                provenance.append(label)
        if analysis.use_eligibility_validation:
            if ELIGIBILITY_VALIDATION_SOURCE not in provenance:
                provenance.append(ELIGIBILITY_VALIDATION_SOURCE)
            validation = analysis.prerequisite_validation
            if validation:
                for source_path in validation.source_paths:
                    label = f"Loaded catalog wiki page [{source_path}]"
                    if label not in provenance:
                        provenance.append(label)
        context = context.model_copy(update={"provenance": provenance})

        blocks = build_course_question_blocks(context=context, analysis=analysis)
        summary = build_course_question_text(analysis=analysis)

        yield StreamEvent(
            type="agent.step.completed",
            label=step_label,
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
            warnings=list(analysis.warnings),
            suggested_prompts=build_course_question_followups(analysis=analysis),
            used_sources=provenance,
        )
