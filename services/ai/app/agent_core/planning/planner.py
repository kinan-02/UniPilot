"""Adaptive Planner (docs/agent/AGENT_VISION.md §3, §3.1): invoked
repeatedly, each time producing only the next runnable chunk of steps --
never a full, upfront plan."""

from __future__ import annotations

import logging
from typing import Any

from app.agent_core.planning.schemas import PlannerInvocationInput, PlannerInvocationOutput, PlanStep
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.reasoning_block import ReasoningBlock
from app.agent_core.reasoning.schemas import ReasoningBlockInput

logger = logging.getLogger(__name__)

PLANNER_OUTPUT_SCHEMA_NAME = "planner_invocation_output_v1"

_PLAN_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "step_id": {"type": "string"},
        "title": {"type": "string"},
        "objective": {"type": "string"},
        "role": {
            "type": "string",
            "enum": [
                "retrieval",
                "interpretation",
                "calculation_validation",
                "simulation_planning",
                "composition",
            ],
        },
        "depends_on": {"type": "array", "items": {"type": "string"}},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "assumptions_to_verify": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
    },
    "required": ["step_id", "title", "objective", "role"],
}

PLANNER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_status": {"type": "string", "enum": ["in_progress", "complete", "blocked_needs_clarification"]},
        "next_steps": {"type": "array", "items": _PLAN_STEP_SCHEMA},
        "plan_summary": {"type": "string"},
        "anticipated_followup": {"type": "array", "items": {"type": "string"}},
        "clarification_question": {"type": ["string", "null"]},
    },
    "required": ["plan_status", "plan_summary"],
}

_FALLBACK_CLARIFICATION = (
    "I wasn't able to determine how to proceed with this request. Could you rephrase it or provide more detail?"
)


def _deterministic_planner_fallback() -> PlannerInvocationOutput:
    return PlannerInvocationOutput(
        plan_status="blocked_needs_clarification",
        next_steps=[],
        plan_summary="Planner reasoning unavailable or failed; no steps could be produced.",
        clarification_question=_FALLBACK_CLARIFICATION,
    )


async def build_next_plan_steps(
    *,
    planner_input: PlannerInvocationInput,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> PlannerInvocationOutput:
    block = ReasoningBlock(llm_adapter=llm_adapter)
    reasoning_input = ReasoningBlockInput(
        block_id=block_id,
        agent_name="planner",
        objective=planner_input.user_goal,
        task_context=planner_input.model_dump(),
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        output_schema=PLANNER_OUTPUT_SCHEMA,
        risk_level="high",
        # A single decisive pass per invocation for now -- multi-pass
        # deliberation quality is exactly the kind of per-step detail this
        # skeleton defers to a later pass, not a structural decision.
        min_reasoning_iterations=1,
        max_reasoning_iterations=1,
    )

    try:
        output = await block.run(reasoning_input)
    except Exception:  # noqa: BLE001 -- the planner must never crash the orchestrator loop
        logger.exception("planner_reasoning_block_raised")
        return _deterministic_planner_fallback()

    if output.status != "completed" or not output.schema_valid or output.result is None:
        return _deterministic_planner_fallback()

    result = output.result
    try:
        next_steps = [PlanStep.model_validate(step) for step in (result.get("next_steps") or [])]
    except Exception:  # noqa: BLE001 -- a malformed step must not crash the loop
        logger.exception("planner_next_steps_invalid")
        return _deterministic_planner_fallback()

    return PlannerInvocationOutput(
        plan_status=result.get("plan_status", "blocked_needs_clarification"),
        next_steps=next_steps,
        plan_summary=result.get("plan_summary", ""),
        anticipated_followup=result.get("anticipated_followup") or [],
        clarification_question=result.get("clarification_question"),
    )


__all__ = ["PLANNER_OUTPUT_SCHEMA_NAME", "PLANNER_OUTPUT_SCHEMA", "build_next_plan_steps"]
