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
from app.services.course_question_service import analyze_course_question


class CourseQuestionWorkflow:
    name = "course_question_workflow"

    async def run(
        self,
        database: AsyncIOMotorDatabase,
        *,
        context: AgentContextPack,
        user_message: str,
    ) -> AsyncIterator[StreamEvent | AgentResponse]:
        yield StreamEvent(
            type="agent.step.started",
            label="Analyzing course eligibility",
            run_id=context.run_id,
        )

        analysis = analyze_course_question(context=context, user_message=user_message)
        blocks = build_course_question_blocks(context=context, analysis=analysis)
        summary = build_course_question_text(analysis=analysis)

        yield StreamEvent(
            type="agent.step.completed",
            label="Analyzing course eligibility",
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
            used_sources=list(context.provenance),
        )
