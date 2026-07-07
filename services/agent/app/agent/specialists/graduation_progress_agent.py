"""Graduation progress specialist agent (Phase 10) — read-only, shadow-only.

Reasons about graduation progress data already computed deterministically
(via `compiled_context`/`dependency_outputs`) — never recalculates credits,
requirement status, or graduation eligibility itself. The live equivalent
today is `app.agent.workflows.graduation_progress_workflow`.
"""

from __future__ import annotations

from typing import Any

from app.agent.reasoning.prompt_registry import SPECIALIST_GRADUATION_PROGRESS_V1
from app.agent.reasoning.reasoning_block import ReasoningBlock
from app.agent.reasoning.task_schemas import SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA
from app.agent.specialists.base import run_specialist_reasoning
from app.agent.specialists.schemas import SpecialistAgentInput, SpecialistAgentOutput
from app.config import Settings

_CONSTRAINTS: list[str] = [
    "Only use compiled_context, dependency_outputs, and deterministic_observations already supplied.",
    "Never invent completed courses, credits, requirement statuses, or graduation eligibility.",
    "Never claim graduation eligibility beyond what compiled_context already states.",
]

_SUCCESS_CRITERIA: list[str] = [
    "Summarize graduation progress using only the supplied deterministic data.",
    "Call out any missing context needed for a confident answer.",
]


async def run_graduation_progress_agent(
    specialist_input: SpecialistAgentInput,
    *,
    reasoning_block: ReasoningBlock | None = None,
    settings: Settings | None = None,
    agent_context_pack: Any | None = None,
) -> SpecialistAgentOutput:
    return await run_specialist_reasoning(
        specialist_input,
        prompt_contract_name=SPECIALIST_GRADUATION_PROGRESS_V1,
        output_schema_name="specialist_graduation_progress_output_v1",
        output_schema=SPECIALIST_GRADUATION_PROGRESS_OUTPUT_SCHEMA,
        risk_level="high",
        constraints=_CONSTRAINTS,
        success_criteria=_SUCCESS_CRITERIA,
        reasoning_block=reasoning_block,
        settings=settings,
        agent_context_pack=agent_context_pack,
    )
