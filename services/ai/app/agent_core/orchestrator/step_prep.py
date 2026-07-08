"""Step-preparation pass (docs/agent/AGENT_VISION.md §7): a small, cheap,
schema-bound reasoning call that decides what one step needs -- separate
from doing the step's actual work (that's the subagent's job)."""

from __future__ import annotations

import logging
from typing import Any

from app.agent_core.planning.schemas import PlanStep
from app.agent_core.planning.state import PlanExecutionState
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.reasoning_block import ReasoningBlock
from app.agent_core.reasoning.schemas import ReasoningBlockInput
from app.agent_core.subagents.schemas import ReasoningParamsOverride, StepInstructionFields, StepPrepOutput

logger = logging.getLogger(__name__)

STEP_PREP_OUTPUT_SCHEMA_NAME = "step_prep_output_v1"

STEP_PREP_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "description": {"type": "string"},
        "specific_instructions": {"type": "array", "items": {"type": "string"}},
        "tone_language_notes": {"type": "string"},
        "context_requirements": {"type": "array", "items": {"type": "string"}},
        "tool_grant_override": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "required": ["goal", "description"],
}


def _deterministic_step_prep_fallback(step: PlanStep) -> StepPrepOutput:
    """Used when reasoning is unavailable or fails -- mirrors the step's own
    declared fields directly rather than guessing anything new."""
    return StepPrepOutput(
        instruction_fields=StepInstructionFields(goal=step.objective, description=step.objective),
        context_requirements=list(step.depends_on),
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=None,
    )


async def run_step_prep(
    *,
    step: PlanStep,
    state: PlanExecutionState,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> StepPrepOutput:
    block = ReasoningBlock(llm_adapter=llm_adapter)
    reasoning_input = ReasoningBlockInput(
        block_id=block_id,
        agent_name="step_prep",
        objective=f"Decide what the step '{step.title}' needs in order to run.",
        task_context={
            "step": step.model_dump(),
            "available_dependency_step_ids": step.depends_on,
        },
        output_schema_name=STEP_PREP_OUTPUT_SCHEMA_NAME,
        output_schema=STEP_PREP_OUTPUT_SCHEMA,
        risk_level="low",
        min_reasoning_iterations=1,
        max_reasoning_iterations=1,
        temperature=0.0,
    )

    try:
        output = await block.run(reasoning_input)
    except Exception:  # noqa: BLE001 -- step-prep must never crash the orchestrator loop
        logger.exception("step_prep_reasoning_block_raised", extra={"stepId": step.step_id})
        return _deterministic_step_prep_fallback(step)

    if output.status != "completed" or not output.schema_valid or output.result is None:
        return _deterministic_step_prep_fallback(step)

    result = output.result
    return StepPrepOutput(
        instruction_fields=StepInstructionFields(
            goal=result.get("goal", step.objective),
            description=result.get("description", step.objective),
            specific_instructions=result.get("specific_instructions") or [],
            tone_language_notes=result.get("tone_language_notes") or "",
        ),
        context_requirements=result.get("context_requirements") or list(step.depends_on),
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=result.get("tool_grant_override"),
    )


__all__ = ["STEP_PREP_OUTPUT_SCHEMA_NAME", "STEP_PREP_OUTPUT_SCHEMA", "run_step_prep"]
