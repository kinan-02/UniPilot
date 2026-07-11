"""`classify_step` -- cheap atomic-vs-complex + role classifier for one
`PlanStep` (docs/agent/AGENT_VISION.md §7, task-handler follow-up).

Replaces `orchestrator/loop.py`'s former `# STOPGAP` keyword-matching
`_stopgap_role_for_step` heuristic with a real, if deliberately cheap,
reasoning-block decision -- bundling role-assignment into the SAME call
that decides whether the step needs `task_handler.py`'s nested-planning
path at all, rather than a separate role-assignment round-trip.

Same single-shot/no-tools/schema-validate-then-repair shape as
`tools/primitives/interpret_text.py`, but configured with much cheaper
`LLMCallParameters` (`thinking_enabled=False`, low reasoning effort, short
timeout) than the Planner's own `thinking_enabled=True`/`medium`/`60s` --
this call needs to be cheap enough to run unconditionally on every step
without becoming the expensive path itself.

Fails CLOSED to `atomic=False` (never a guessed role): a wrongly-atomic
verdict risks a silently incomplete downstream result (the specialist result
would be checked against `success_criteria` and might pass that check
anyway, but there's no reason to bet on it); a wrongly-non-atomic verdict
only costs one extra, bounded planning round via `task_handler.py`'s own
private sub-plan. The asymmetry is deliberate.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import Field

from app.agent_core.planning.schemas import PlanStep, RoleName, StateEntrySummary
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters

TASK_HANDLER_CLASSIFIER_V1 = "task_handler_classifier_v1"
_OUTPUT_SCHEMA_NAME = "task_handler_classifier_output_v1"
_MAX_SCHEMA_REPAIR_ATTEMPTS = 1  # cheap primitive -- bounded tighter than the Planner's own 2

_ROLE_VALUES: tuple[str, ...] = (
    "retrieval",
    "interpretation",
    "calculation_validation",
    "simulation_planning",
    "composition",
)

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "atomic": {"type": "boolean"},
        "role_if_atomic": {"type": ["string", "null"], "enum": [*_ROLE_VALUES, None]},
    },
    "required": ["atomic", "role_if_atomic"],
    "additionalProperties": False,
}


class TaskHandlerClassifierInput(BaseReasoningBlockInput):
    step: PlanStep
    dependency_context: list[StateEntrySummary] = Field(default_factory=list)


class _ClassifierBlockOutput(BaseReasoningBlockOutput):
    atomic: bool = False
    role_if_atomic: RoleName | None = None


def _task_handler_classifier_contract() -> PromptContract:
    return PromptContract(
        name=TASK_HANDLER_CLASSIFIER_V1,
        version="1.0.0",
        role_prompt=(
            "You are a fast triage classifier for the UniPilot Agent's task handler. You are given "
            "one plan step (its objective, success_criteria, and assumptions_to_verify) and must "
            "decide two things in one pass: whether this step reduces to ONE specialist subagent "
            "call (\"atomic\"), and if so, which of the five specialist roles should handle it."
        ),
        instructions=[
            "If success_criteria describes several distinct facts, computations, or labeled "
            "sub-parts (e.g. 'cumulative GPA AND semester GPAs for the last two semesters AND "
            "course/credit details, labeled by semester'), treat the step as NOT atomic -- one "
            "specialist call is unlikely to reliably cover all of it.",
            "role_if_atomic must be null whenever atomic is false -- a non-atomic step gets "
            "decomposed by the task handler's own nested planner, which decides roles for its own "
            "sub-steps separately; this call never assigns a role to a step it judged non-atomic.",
            f"When atomic is true, role_if_atomic must be exactly one of: {', '.join(_ROLE_VALUES)}.",
            "When genuinely uncertain whether a step is atomic, prefer atomic=false. A wrongly "
            "non-atomic verdict only costs one extra bounded planning round; a wrongly atomic "
            "verdict risks silently returning an incomplete result.",
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


def build_task_handler_classifier_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_task_handler_classifier_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: TaskHandlerClassifierInput) -> str:
    payload = {
        "step": block_input.step.model_dump(),
        "dependency_context": [entry.model_dump() for entry in block_input.dependency_context],
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class TaskHandlerClassifierReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails CLOSED to `atomic=False`/`role_if_atomic=None`
    on any failure path -- schema-repair exhaustion, a raised error, or the
    model's own output missing a required field."""

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_task_handler_classifier_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: TaskHandlerClassifierInput, telemetry: RunTelemetry
    ) -> _ClassifierBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or TASK_HANDLER_CLASSIFIER_V1)
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

    def _to_output(self, normalized: dict[str, Any]) -> _ClassifierBlockOutput:
        atomic = normalized.get("atomic")
        role_if_atomic = normalized.get("role_if_atomic")

        if not isinstance(atomic, bool):
            return self._fallback_output(extra_warning="atomic_field_not_boolean")
        # A hollow/inconsistent verdict (atomic=true with no role, or
        # atomic=false with a role anyway) fails closed too -- schema
        # validation alone can't express this cross-field constraint.
        if atomic and role_if_atomic not in _ROLE_VALUES:
            return self._fallback_output(extra_warning="atomic_true_missing_valid_role")
        if not atomic and role_if_atomic is not None:
            role_if_atomic = None

        return _ClassifierBlockOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0 if atomic else 0.0,
            atomic=atomic,
            role_if_atomic=role_if_atomic,
        )

    def _fallback_output(self, *, extra_warning: str | None = None) -> _ClassifierBlockOutput:
        warnings = ["task_handler_classifier_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return _ClassifierBlockOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            atomic=False,
            role_if_atomic=None,
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _ClassifierBlockOutput:
        return self._fallback_output(extra_warning=f"reasoning_block_failed: {reason}")


async def classify_step(
    *,
    step: PlanStep,
    dependency_context: list[StateEntrySummary],
    llm_adapter: LLMAdapter,
    block_id: str,
) -> _ClassifierBlockOutput:
    block = TaskHandlerClassifierReasoningBlock(llm_adapter=llm_adapter)
    return await block.run(
        TaskHandlerClassifierInput(
            block_id=block_id,
            agent_name="task_handler_classifier",
            objective=step.objective,
            output_schema_name=_OUTPUT_SCHEMA_NAME,
            output_schema=_OUTPUT_SCHEMA,
            prompt_contract_name=TASK_HANDLER_CLASSIFIER_V1,
            step=step,
            dependency_context=dependency_context,
            llm_call_parameters=LLMCallParameters(
                thinking_enabled=False,
                reasoning_effort="low",
                timeout=15.0,
                max_retries=1,
            ),
        )
    )


__all__ = [
    "TASK_HANDLER_CLASSIFIER_V1",
    "TaskHandlerClassifierInput",
    "TaskHandlerClassifierReasoningBlock",
    "build_task_handler_classifier_prompt_registry",
    "classify_step",
]
