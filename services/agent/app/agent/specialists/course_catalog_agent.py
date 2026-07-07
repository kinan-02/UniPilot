"""Course catalog specialist agent (Phase 10) — read-only, shadow-only.

Reasons about course/catalog/offering questions using only data already
present in `compiled_context` — never invents a course number, prerequisite,
or offering. The live equivalent today is
`app.agent.workflows.course_question_workflow`.
"""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.prompt_registry import SPECIALIST_COURSE_CATALOG_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.task_schemas import SPECIALIST_COURSE_CATALOG_OUTPUT_SCHEMA
from app.agent.specialists.base import run_specialist_reasoning
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentOutput
from app.config import Settings

_CONSTRAINTS: list[str] = [
    "Only use compiled_context, dependency_outputs, and deterministic_observations already supplied.",
    "Never invent a course number, prerequisite, offering, or catalog rule.",
    "Never claim a course is offered/eligible beyond what compiled_context already states.",
]

_SUCCESS_CRITERIA: list[str] = [
    "Answer the course/catalog question using only the supplied deterministic data.",
    "Call out any missing context needed for a confident answer.",
]


async def run_course_catalog_agent(
    specialist_input: SpecialistAgentInput,
    *,
    reasoning_block: ReasoningBlock | None = None,
    settings: Settings | None = None,
    agent_context_pack: Any | None = None,
) -> SpecialistAgentOutput:
    return await run_specialist_reasoning(
        specialist_input,
        prompt_contract_name=SPECIALIST_COURSE_CATALOG_V1,
        output_schema_name="specialist_course_catalog_output_v1",
        output_schema=SPECIALIST_COURSE_CATALOG_OUTPUT_SCHEMA,
        risk_level="medium",
        constraints=_CONSTRAINTS,
        success_criteria=_SUCCESS_CRITERIA,
        reasoning_block=reasoning_block,
        settings=settings,
        agent_context_pack=agent_context_pack,
    )
