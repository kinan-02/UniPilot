"""Merged `classify_step` + `step_prep` -- a single, cheap reasoning-block
decision that determines both atomic-vs-complex/role assignment and the
execution preparation (goal, context requirements) in one LLM call.

Replaces `task_handler_classifier.py` and `step_prep.py` to halve the
per-step overhead.

Same single-shot/no-tools/schema-validate-then-repair shape as the original
classifier, configured with `thinking_enabled=False`, low reasoning effort,
and a 20s timeout.

Fails CLOSED to `atomic=False` (never a guessed role): a wrongly-atomic
verdict risks a silently incomplete downstream result.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import Field

from app.agent_core.planning.schemas import PlanStep, RoleName, StateEntrySummary
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.subagents.schemas import StepInstructionFields, StepPrepOutput, ReasoningParamsOverride

logger = logging.getLogger(__name__)

TASK_HANDLER_CLASSIFY_AND_PREP_V1 = "task_handler_classify_and_prep_v1"
_OUTPUT_SCHEMA_NAME = "task_handler_classify_and_prep_output_v1"
_MAX_SCHEMA_REPAIR_ATTEMPTS = 1  # cheap primitive -- bounded tighter than the Planner's own 2
_TIMEOUT_SECONDS = 20.0  # uses step_prep's 20s, not classifier's 15s

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
        "goal": {"type": ["string", "null"]},
        "description": {"type": ["string", "null"]},
        "specific_instructions": {"type": ["array", "null"], "items": {"type": "string"}},
        "tone_language_notes": {"type": ["string", "null"]},
        "context_requirements": {"type": ["array", "null"], "items": {"type": "string"}},
        "tool_grant_override": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "required": ["atomic", "role_if_atomic"],
    "additionalProperties": False,
}

class ClassifyAndPrepInput(BaseReasoningBlockInput):
    step: PlanStep
    dependency_context: list[StateEntrySummary] = Field(default_factory=list)


class _ClassifyAndPrepOutput(BaseReasoningBlockOutput):
    atomic: bool = False
    role_if_atomic: RoleName | None = None
    goal: str | None = None
    description: str | None = None
    specific_instructions: list[str] | None = None
    tone_language_notes: str | None = None
    context_requirements: list[str] | None = None
    tool_grant_override: list[str] | None = None


def _classify_and_prep_contract() -> PromptContract:
    return PromptContract(
        name=TASK_HANDLER_CLASSIFY_AND_PREP_V1,
        version="1.0.0",
        role_prompt=(
            "You are a fast triage classifier and step-prep assistant for the UniPilot Agent's "
            "task handler. You are given one plan step (its objective, success_criteria, and "
            "assumptions_to_verify) and must decide two things in one pass: whether this step "
            "reduces to ONE specialist subagent call (\"atomic\") and which role, AND what the "
            "step needs in order to run (goal, description, specific_instructions, etc)."
        ),
        instructions=[
            "EXCEPTION to the non-atomic rules: The system provides high-level composite tools that can handle complex multi-step logic in one shot. If a step's objective naturally maps to one of these (e.g. 'audit graduation progress', 'check eligibility', 'simulate course disruption', 'compare plans', 'find requirement substitutes'), treat the step AS ATOMIC (`atomic=True`) and assign `role_if_atomic='simulation_planning'`, rather than defaulting to `atomic=False` and decomposing it.",
            "If success_criteria describes several distinct facts, computations, or labeled "
            "sub-parts (e.g. 'cumulative GPA AND semester GPAs for the last two semesters AND "
            "course/credit details, labeled by semester'), treat the step as NOT atomic -- one "
            "specialist call is unlikely to reliably cover all of it.",
            "role_if_atomic must be null whenever atomic is false -- a non-atomic step gets "
            "decomposed by the task handler's own nested planner, which decides roles for its own "
            "sub-steps separately; this call never assigns a role to a step it judged non-atomic.",
            "If success_criteria asks for a course's or program's REQUIREMENT-FULFILLMENT status "
            "(e.g. mandatory, elective, core, which track/degree requirement it satisfies) bundled "
            "together with structural catalog fields (course code, credits, prerequisites), treat "
            "the step as NOT atomic: that status lives in prose and needs interpret_text, which is "
            "granted only to the interpretation role, never retrieval -- retrieval cannot honestly "
            "satisfy that half of the criteria.",
            "If success_criteria asks for a cumulative GPA, semester GPA, or academic-standing/"
            "probation status as if it were a directly fetchable field (rather than explicitly "
            "asking only for raw per-course grades and credits), treat the step as NOT atomic: a "
            "GPA/standing value is DERIVED by applying a rule to raw grades, which retrieval alone "
            "has no tool to do -- never assign role_if_atomic='retrieval' to a step whose criteria "
            "expects an already-computed GPA or standing label back.",
            f"When atomic is true, role_if_atomic must be exactly one of: {', '.join(_ROLE_VALUES)}.",
            "When genuinely uncertain whether a step is atomic, prefer atomic=false. A wrongly "
            "non-atomic verdict only costs one extra bounded planning round; a wrongly atomic "
            "verdict risks silently returning an incomplete result.",
            "If atomic=false, the prep fields (goal, description, specific_instructions, etc.) "
            "are meaningless and should be null.",
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


def build_classify_and_prep_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_classify_and_prep_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt, "", "INSTRUCTIONS:"]
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: ClassifyAndPrepInput) -> str:
    payload = {
        "step": block_input.step.model_dump(),
        "dependency_context": [entry.model_dump() for entry in block_input.dependency_context],
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class TaskHandlerClassifyAndPrepBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails CLOSED to `atomic=False`/`role_if_atomic=None`."""

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_classify_and_prep_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: ClassifyAndPrepInput, telemetry: RunTelemetry
    ) -> _ClassifyAndPrepOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or TASK_HANDLER_CLASSIFY_AND_PREP_V1)
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

    def _to_output(self, normalized: dict[str, Any]) -> _ClassifyAndPrepOutput:
        atomic = normalized.get("atomic")
        role_if_atomic = normalized.get("role_if_atomic")

        if not isinstance(atomic, bool):
            return self._fallback_output(extra_warning="atomic_field_not_boolean")
        if atomic and role_if_atomic not in _ROLE_VALUES:
            return self._fallback_output(extra_warning="atomic_true_missing_valid_role")
        if not atomic and role_if_atomic is not None:
            role_if_atomic = None

        return _ClassifyAndPrepOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0 if atomic else 0.0,
            atomic=atomic,
            role_if_atomic=role_if_atomic,
            goal=normalized.get("goal"),
            description=normalized.get("description"),
            specific_instructions=normalized.get("specific_instructions"),
            tone_language_notes=normalized.get("tone_language_notes"),
            context_requirements=normalized.get("context_requirements"),
            tool_grant_override=normalized.get("tool_grant_override"),
        )

    def _fallback_output(self, *, extra_warning: str | None = None) -> _ClassifyAndPrepOutput:
        warnings = ["task_handler_classify_and_prep_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return _ClassifyAndPrepOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            atomic=False,
            role_if_atomic=None,
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _ClassifyAndPrepOutput:
        return self._fallback_output(extra_warning=f"reasoning_block_failed: {reason}")


def _user_id_instruction(user_id: str) -> str:
    return (
        f"The current student's own user_id (for get_entity with entity_type="
        f"'student_profile'/'completed_courses'/'semester_plan') is: {user_id}"
    )


def _deterministic_step_prep_fallback(step: PlanStep, *, user_id: str) -> StepPrepOutput:
    return StepPrepOutput(
        instruction_fields=StepInstructionFields(
            goal=step.objective,
            description=step.objective,
            specific_instructions=[_user_id_instruction(user_id)],
        ),
        context_requirements=list(step.depends_on),
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=None,
    )


async def classify_and_prep_step(
    *,
    step: PlanStep,
    dependency_context: list[StateEntrySummary],
    llm_adapter: LLMAdapter,
    block_id: str,
    user_id: str,
) -> tuple[_ClassifyAndPrepOutput, StepPrepOutput]:
    block = TaskHandlerClassifyAndPrepBlock(llm_adapter=llm_adapter)
    try:
        output = await block.run(
            ClassifyAndPrepInput(
                block_id=block_id,
                agent_name="task_handler_classify_and_prep",
                objective=f"Classify and decide what the step '{step.objective}' needs in order to run.",
                output_schema_name=_OUTPUT_SCHEMA_NAME,
                output_schema=_OUTPUT_SCHEMA,
                prompt_contract_name=TASK_HANDLER_CLASSIFY_AND_PREP_V1,
                step=step,
                dependency_context=dependency_context,
                llm_call_parameters=LLMCallParameters(
                    thinking_enabled=False,
                    reasoning_effort="low",
                    timeout=_TIMEOUT_SECONDS,
                    max_retries=1,
                ),
            )
        )
    except Exception:
        logger.exception("classify_and_prep_reasoning_block_raised", extra={"stepId": step.step_id})
        # Fails closed
        output = block._fallback_output(extra_warning="exception_raised")
    
    # If it failed to complete or was invalid, build deterministic fallback for prep
    if output.status != "completed" or not output.schema_valid or output.result is None:
        return output, _deterministic_step_prep_fallback(step, user_id=user_id)

    # Building StepPrepOutput for atomic steps
    specific_instructions = [*(output.specific_instructions or []), _user_id_instruction(user_id)]
    step_prep_output = StepPrepOutput(
        instruction_fields=StepInstructionFields(
            goal=output.goal or step.objective,
            description=output.description or step.objective,
            specific_instructions=specific_instructions,
            tone_language_notes=output.tone_language_notes or "",
        ),
        context_requirements=output.context_requirements or list(step.depends_on),
        reasoning_params=ReasoningParamsOverride(),
        output_schema_name="generic_step_output_v1",
        output_schema={"type": "object"},
        tool_grant_override=output.tool_grant_override,
    )
    return output, step_prep_output


__all__ = [
    "TASK_HANDLER_CLASSIFY_AND_PREP_V1",
    "ClassifyAndPrepInput",
    "TaskHandlerClassifyAndPrepBlock",
    "build_classify_and_prep_prompt_registry",
    "classify_and_prep_step",
]
