"""`check_success_criteria` -- verifies a specialist's result actually covers
a `PlanStep`'s own declared `success_criteria` (docs/agent/AGENT_VISION.md
§7, task-handler follow-up).

Genuinely new logic: `orchestrator/monitor.py::evaluate_step_result` is
purely status-based and never reads `success_criteria` at all (its own
docstring flags this as a stopgap too). A specialist can self-report
`status="succeeded"` while still not covering everything a step's
`success_criteria` asked for -- e.g. fetched cumulative GPA but missed the
last-two-semesters breakdown the step actually needed. This primitive is
`orchestrator/task_handler.py`'s fast-path check: if it comes back False,
the task handler falls back to its own nested-planning path as a
second-line safety net, not the primary mechanism.

Same single-shot/no-tools/schema-validate-then-repair shape as
`tools/primitives/interpret_text.py`, cheap `LLMCallParameters`, and fails
CLOSED to `False` on any failure path.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from app.agent_core.planning.schemas import PlanStep
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.subagents.schemas import SubagentResult

TASK_HANDLER_SUCCESS_CHECK_V1 = "task_handler_success_check_v1"
_OUTPUT_SCHEMA_NAME = "task_handler_success_check_output_v1"
_MAX_SCHEMA_REPAIR_ATTEMPTS = 1

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "criteria_met": {"type": "boolean"},
        "unmet_criteria": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["criteria_met", "unmet_criteria"],
    "additionalProperties": False,
}


class SuccessCriteriaCheckInput(BaseReasoningBlockInput):
    step: PlanStep
    specialist_result: dict[str, Any] = Field(default_factory=dict)


class _SuccessCheckBlockOutput(BaseReasoningBlockOutput):
    criteria_met: bool = False
    unmet_criteria: list[str] = Field(default_factory=list)


def _task_handler_success_check_contract() -> PromptContract:
    return PromptContract(
        name=TASK_HANDLER_SUCCESS_CHECK_V1,
        version="1.0.0",
        role_prompt=(
            "You are a fast verification check for the UniPilot Agent's task handler. You are given "
            "one plan step's success_criteria and the actual data a specialist subagent returned for "
            "it. Decide whether that data genuinely satisfies every stated success criterion."
        ),
        instructions=[
            "Check each success criterion independently -- a result can satisfy some criteria and "
            "not others; list every criterion NOT satisfied in unmet_criteria, verbatim.",
            "criteria_met is true only when unmet_criteria is empty.",
            "Do not reward a plausible-looking but incomplete result -- if a criterion asks for "
            "multiple labeled parts (e.g. 'semester GPAs for the last two semesters') and only one "
            "part is present, that criterion is NOT met.",
            "When genuinely uncertain whether a criterion is met, prefer NOT met -- a false negative "
            "here only costs one extra bounded planning round; a false positive silently ships an "
            "incomplete result to the rest of the plan.",
        ],
        allowed_context_fields=None,
        output_schema_name=_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
        ],
    )


def build_task_handler_success_check_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_task_handler_success_check_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: SuccessCriteriaCheckInput) -> str:
    payload = {
        "success_criteria": block_input.step.success_criteria,
        "specialist_result": block_input.specialist_result,
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class SuccessCriteriaCheckReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails CLOSED to `criteria_met=False` -- never
    silently accept an unverifiable result as complete."""

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_task_handler_success_check_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: SuccessCriteriaCheckInput, telemetry: RunTelemetry
    ) -> _SuccessCheckBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or TASK_HANDLER_SUCCESS_CHECK_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)

        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=_build_user_prompt(block_input),
            params=params,
            response_schema=block_input.output_schema,
            phase="pass1_of_1",
            block_input=block_input,
            telemetry=telemetry,
        )

        normalized = self._normalize_result(call_result.parsed, output_schema=block_input.output_schema)
        validation = self._validate_schema(normalized, block_input.output_schema)
        if not validation.valid:
            repair_outcome = await self._repair_schema(
                initial_result=normalized,
                initial_errors=validation.errors,
                output_schema=block_input.output_schema,
                max_attempts=_MAX_SCHEMA_REPAIR_ATTEMPTS,
                block_input=block_input,
                telemetry=telemetry,
            )
            if not repair_outcome.valid:
                return self._fallback_output(extra_warning="schema_validation_failed")
            normalized = repair_outcome.result

        return self._to_output(normalized)

    def _to_output(self, normalized: dict[str, Any]) -> _SuccessCheckBlockOutput:
        criteria_met = normalized.get("criteria_met")
        unmet_criteria = normalized.get("unmet_criteria")

        if not isinstance(criteria_met, bool) or not isinstance(unmet_criteria, list):
            return self._fallback_output(extra_warning="malformed_check_output")
        # A hollow/inconsistent verdict (criteria_met=true with unmet
        # criteria listed anyway) fails closed too.
        if criteria_met and unmet_criteria:
            return self._fallback_output(extra_warning="criteria_met_true_with_unmet_criteria_listed")

        return _SuccessCheckBlockOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0 if criteria_met else 0.0,
            criteria_met=criteria_met,
            unmet_criteria=unmet_criteria,
        )

    def _fallback_output(self, *, extra_warning: str | None = None) -> _SuccessCheckBlockOutput:
        warnings = ["task_handler_success_check_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return _SuccessCheckBlockOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            criteria_met=False,
            unmet_criteria=[],
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _SuccessCheckBlockOutput:
        return self._fallback_output(extra_warning=f"reasoning_block_failed: {reason}")


async def check_success_criteria(
    *,
    step: PlanStep,
    result: SubagentResult,
    llm_adapter: LLMAdapter,
    block_id: str,
) -> bool:
    if not step.success_criteria:
        return True  # nothing declared to check against -- no LLM call needed

    block = SuccessCriteriaCheckReasoningBlock(llm_adapter=llm_adapter)
    output = await block.run(
        SuccessCriteriaCheckInput(
            block_id=block_id,
            agent_name="task_handler_success_check",
            objective=f"Check whether the result satisfies: {'; '.join(step.success_criteria)}",
            output_schema_name=_OUTPUT_SCHEMA_NAME,
            output_schema=_OUTPUT_SCHEMA,
            prompt_contract_name=TASK_HANDLER_SUCCESS_CHECK_V1,
            step=step,
            specialist_result=result.result or {},
            llm_call_parameters=LLMCallParameters(
                thinking_enabled=False,
                reasoning_effort="low",
                timeout=15.0,
                max_retries=1,
            ),
        )
    )
    return bool(output.criteria_met)


__all__ = [
    "TASK_HANDLER_SUCCESS_CHECK_V1",
    "SuccessCriteriaCheckInput",
    "SuccessCriteriaCheckReasoningBlock",
    "build_task_handler_success_check_prompt_registry",
    "check_success_criteria",
]
