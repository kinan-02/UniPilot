"""Specialist Router (docs/planning/SPECIALIST_ROUTER_PLANNER_SPLIT_PLAN.md).

Replaces the merged `classify_and_prep` + nested-planner path. Given ONE plan
step, it produces the PIPELINE of specialist subagents that will execute it --
"atomic vs complex" is a cardinality question about specialist TYPES, so a
single-specialist step is just a length-1 pipeline (classification is
decomposition at N=1).

One fast, no-thinking, single-shot call. It reasons only about WHICH specialist
types are needed and how their outputs chain (retrieval -> calculation for a
derived GPA; retrieval -> interpretation for a policy's meaning) -- the
specialists themselves own the tools. Its model of what each specialist can and
cannot do is rendered from the roster (`roles/catalog.py`), so it cannot drift
from what the specialists actually do.

Fails CLOSED to a single retrieval sub-step mirroring the parent objective: a
route it cannot produce becomes a best-effort fetch that the outer Monitor +
success-check still verify, never a silent pass. Genuine clarification and
content-adaptive branching are the top-level Planner's job, not the router's.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.agent_core.planning.schemas import PlanStep, RoleName, StateEntrySummary
from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters
from app.agent_core.roles.catalog import render_specialist_catalog
from app.agent_core.roles.roster import build_default_role_roster
from app.agent_core.roles.schemas import RoleDefinition

logger = logging.getLogger(__name__)

SPECIALIST_ROUTER_V1 = "specialist_router_v1"
_OUTPUT_SCHEMA_NAME = "specialist_pipeline_v1"
_MAX_SCHEMA_REPAIR_ATTEMPTS = 1  # cheap primitive, same bound as the old classifier
_TIMEOUT_SECONDS = 20.0

_ROLE_VALUES: tuple[str, ...] = (
    "retrieval",
    "interpretation",
    "calculation_validation",
    "simulation_planning",
    "composition",
)

_SUB_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "sub_step_id": {"type": "string"},
        "specialist": {"type": "string", "enum": [*_ROLE_VALUES]},
        "objective": {"type": "string"},
        "depends_on": {"type": "array", "items": {"type": "string"}},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "specific_instructions": {"type": ["array", "null"], "items": {"type": "string"}},
        "context_requirements": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "required": ["sub_step_id", "specialist", "objective"],
    "additionalProperties": False,
}

_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"pipeline": {"type": "array", "items": _SUB_STEP_SCHEMA}},
    "required": ["pipeline"],
    "additionalProperties": False,
}

SPECIALIST_PLAN_ROUTER_V1 = "specialist_plan_router_v1"
_PLAN_OUTPUT_SCHEMA_NAME = "specialist_plan_router_output_v1"

# One call routes N steps, so it cannot be held to one step's time budget.
_PLAN_TIMEOUT_SECONDS = _TIMEOUT_SECONDS * 3

_PLAN_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "step_id": {"type": "string"},
                    "pipeline": {"type": "array", "items": _SUB_STEP_SCHEMA},
                },
                "required": ["step_id", "pipeline"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["routes"],
    "additionalProperties": False,
}


class RoutedSubStep(BaseModel):
    """One specialist invocation in a step's pipeline. `specialist` is a real
    `RoleName` (pydantic rejects anything else, so a hallucinated specialist
    name never survives into a dispatch)."""

    sub_step_id: str
    specialist: RoleName
    objective: str
    depends_on: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    specific_instructions: list[str] = Field(default_factory=list)
    context_requirements: list[str] = Field(default_factory=list)

    @field_validator(
        "depends_on",
        "success_criteria",
        "specific_instructions",
        "context_requirements",
        mode="before",
    )
    @classmethod
    def _null_list_means_empty(cls, value: Any) -> Any:
        """Accept exactly what `_SUB_STEP_SCHEMA` advertises.

        The schema declares `specific_instructions`/`context_requirements` as
        `{"type": ["array", "null"]}`, so `null` is a CORRECT model response --
        but `list[str]` rejects it. The sub-step was then dropped as "invalid"
        (`specialist_router_dropped_invalid_substep`), the pipeline emptied, and
        `_fail_closed_pipeline` silently downgraded the whole step to a blind
        RETRIEVAL fetch.

        Measured live (2026-07-15): the router correctly routed "Calculate the
        total credits..." to `calculation_validation` with
        `context_requirements: null`, was dropped for saying null, and retrieval
        inherited the step -- doing 17-number mental math, returning 63.0
        (truth: 62.5) and stamping it `official_record` / confidence 1.0.
        Punishing the model for obeying our own schema is our bug, not its.
        """
        return [] if value is None else value


class SpecialistRouterOutput(BaseReasoningBlockOutput):
    pipeline: list[RoutedSubStep] = Field(default_factory=list)

    @property
    def is_atomic(self) -> bool:
        return len(self.pipeline) == 1


class SpecialistRouterInput(BaseReasoningBlockInput):
    step: PlanStep
    dependency_context: list[StateEntrySummary] = Field(default_factory=list)
    specialist_catalog: str = ""
    # Populated only on a REPAIR re-route: what a prior attempt at this step
    # was missing (unmet success-criteria). Surfaced to the model so the new
    # pipeline addresses the specific gap instead of reproducing the same one.
    failure_context: list[str] = Field(default_factory=list)


def _router_contract() -> PromptContract:
    return PromptContract(
        name=SPECIALIST_ROUTER_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Specialist Router for the UniPilot Agent's task handler. You are given "
            "ONE plan step (its objective, success_criteria, and the results it depends on) and "
            "must decide the PIPELINE of specialist subagents that will execute it. You do not use "
            "tools and you do not do the work yourself -- the specialists own the tools; you decide "
            "WHICH specialist types are needed and how their outputs chain. A step that one "
            "specialist can fully complete is a one-element pipeline (that is what 'atomic' means)."
        ),
        instructions=[
            "Route each sub-step to exactly ONE specialist from the SPECIALISTS catalog below. Use "
            "the FEWEST specialists that fully cover the step -- never add a sub-step to look "
            "thorough.",
            "If a single specialist can complete the whole step, return a one-element pipeline. Do "
            "not decompose an atomic step.",
            "A value that must be DERIVED -- cumulative/semester GPA, academic-standing/probation "
            "status, credit totals, a threshold comparison -- needs a retrieval sub-step to fetch "
            "the raw facts AND a calculation_validation sub-step (depending on it) to compute the "
            "value. Never route a derivation to retrieval; retrieval cannot compute.",
            "A course's or program's requirement-fulfillment status (mandatory/elective/which "
            "requirement it satisfies), or the meaning/implications of a policy or regulation, needs "
            "a retrieval sub-step to fetch the text AND an interpretation sub-step (depending on it) "
            "to read it. Never route interpretation to retrieval.",
            "'The current semester' / 'next semester' is a SINGLE retrieval sub-step (retrieval owns "
            "get_current_semester, which returns both) -- never a calculation sub-step to compute a "
            "semester code.",
            "A step that maps to a simulation_planning composite -- a 'can I take X' eligibility "
            "check, a graduation-progress audit, a fail-course-X what-if, a plan comparison, a "
            "requirement-substitute search -- is ONE simulation_planning sub-step (atomic). That "
            "composite already performs the multi-step work internally; do not hand-decompose it.",
            "depends_on lists the sibling sub_step_ids whose OUTPUT this sub-step consumes. A "
            "sub-step that needs data produced by one of the parent step's own dependencies "
            "references that dependency's EXISTING id (shown in dependency_context) directly, "
            "verbatim -- never a prose description.",
            "Each sub-step's success_criteria is the MINIMUM that makes its own result usable by the "
            "next sub-step or the final answer. State it as a plain OUTCOME ('completed courses "
            "retrieved', 'cumulative GPA computed', 'prerequisites for the course identified'), "
            "NEVER as a data shape, field path, or format ('returned as a list where each item has "
            "metadata.courseNumber and creditsEarned', 'includes degreeId and trackSlug') -- the "
            "specialist owns the shape, and a shape-based criterion makes the downstream check fail "
            "even when the result is correct. Concrete and checkable, never a vague hedge.",
            "Include a composition sub-step (last) only when the step must itself produce "
            "user-facing prose, rather than a fact a later plan step will consume.",
            "Never produce branching ('if s1 shows X, do s2, else s3'). Produce the single best "
            "static pipeline; if a sub-step fails at run time you will be re-invoked with that "
            "failure to adjust.",
        ],
        allowed_context_fields=None,
        output_schema_name=_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Route only to specialists that appear in the SPECIALISTS catalog -- never invent one.",
        ],
    )


def _plan_router_contract() -> PromptContract:
    """The batch sibling of `_router_contract`.

    Reuses that contract's `instructions` and `safety_rules` VERBATIM -- every
    one of them is a rule about routing a single step to a pipeline, and holds
    unchanged when several steps are routed in one call. Duplicating them here
    (rather than sharing) is exactly how the two would drift apart.

    Only the role prompt differs: it must say the steps arrive as a batch, must
    be routed independently of one another, and -- unlike the per-step router --
    come with no results, because nothing has run yet.
    """
    base = _router_contract()
    return PromptContract(
        name=SPECIALIST_PLAN_ROUTER_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Specialist Router for the UniPilot Agent's task handler. You are given "
            "EVERY step of a plan at once, and must decide for EACH one the PIPELINE of specialist "
            "subagents that will execute it. You do not use tools and you do not do the work "
            "yourself -- the specialists own the tools; you decide WHICH specialist types are needed "
            "and how their outputs chain. A step that one specialist can fully complete is a "
            "one-element pipeline (that is what 'atomic' means); most steps are.\n\n"
            "Return one entry per step you were given, keyed by its exact step_id. Route each step "
            "on its OWN objective and success_criteria -- how you route one step never changes how "
            "you route another.\n\n"
            "These steps have NOT run yet, so you are shown no results -- only what each step is "
            "asking for, and the step_ids it depends on. Route on the ask. Do not speculate about "
            "what a dependency will return; if a step's dependencies later come back failed or "
            "incomplete, that step is re-routed at dispatch with those real results in hand."
        ),
        instructions=base.instructions,
        allowed_context_fields=None,
        output_schema_name=_PLAN_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=base.safety_rules,
    )


def build_specialist_router_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_router_contract())
    registry.register(_plan_router_contract())
    return registry


def _build_system_prompt(contract: PromptContract, specialist_catalog: str) -> str:
    lines = [contract.role_prompt, "", "SPECIALISTS (route each sub-step to exactly one):", specialist_catalog]
    lines.append("")
    lines.append("INSTRUCTIONS:")
    lines.extend(f"- {item}" for item in contract.instructions)
    lines.append("")
    lines.append("SAFETY RULES:")
    lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: SpecialistRouterInput) -> str:
    payload: dict[str, Any] = {
        "step": block_input.step.model_dump(),
        "dependency_context": [entry.model_dump() for entry in block_input.dependency_context],
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    if block_input.failure_context:
        # A prior pipeline for this step fell short here -- the new route must
        # cover these gaps, not reproduce them.
        payload["prior_attempt_was_missing"] = block_input.failure_context
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _fail_closed_pipeline(step: PlanStep) -> list[RoutedSubStep]:
    """The one route every failure resolves to: a single retrieval sub-step
    mirroring the parent objective. The outer Monitor + success-check still
    verify it, so a route the model could not produce degrades to a best-effort
    fetch, never a silent pass or a crash."""
    return [
        RoutedSubStep(
            sub_step_id="s1",
            specialist="retrieval",
            objective=step.objective,
            depends_on=[],
            success_criteria=list(step.success_criteria),
        )
    ]


class SpecialistRouterBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails CLOSED to a single retrieval sub-step."""

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_specialist_router_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: SpecialistRouterInput, telemetry: RunTelemetry
    ) -> SpecialistRouterOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or SPECIALIST_ROUTER_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)

        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract, block_input.specialist_catalog),
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
                return self._fallback_output(block_input, extra_warning="schema_validation_failed")
            normalized = repair_outcome.result

        return self._to_output(normalized, block_input)

    def _to_output(
        self, normalized: dict[str, Any], block_input: SpecialistRouterInput
    ) -> SpecialistRouterOutput:
        raw_pipeline = normalized.get("pipeline")
        if not isinstance(raw_pipeline, list):
            return self._fallback_output(block_input, extra_warning="pipeline_not_a_list")

        pipeline: list[RoutedSubStep] = []
        for item in raw_pipeline:
            if not isinstance(item, dict):
                continue
            try:
                # A sub-step naming a non-existent specialist fails RoleName
                # validation here and is dropped, never dispatched.
                pipeline.append(RoutedSubStep.model_validate(item))
            except Exception:  # noqa: BLE001 -- one malformed sub-step must not sink the route
                logger.warning("specialist_router_dropped_invalid_substep", extra={"stepId": block_input.step.step_id})

        if not pipeline:
            return self._fallback_output(block_input, extra_warning="empty_or_all_invalid_pipeline")

        return SpecialistRouterOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0,
            pipeline=pipeline,
        )

    def _fallback_output(
        self, block_input: SpecialistRouterInput, *, extra_warning: str | None = None
    ) -> SpecialistRouterOutput:
        warnings = ["specialist_router_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return SpecialistRouterOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            pipeline=_fail_closed_pipeline(block_input.step),
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> SpecialistRouterOutput:
        assert isinstance(block_input, SpecialistRouterInput)
        return self._fallback_output(block_input, extra_warning=f"reasoning_block_failed: {reason}")


async def route_step(
    *,
    step: PlanStep,
    dependency_context: list[StateEntrySummary],
    llm_adapter: LLMAdapter,
    block_id: str,
    user_id: str,
    role_roster: dict[RoleName, RoleDefinition] | None = None,
    failure_context: list[str] | None = None,
) -> SpecialistRouterOutput:
    """Route one step to its specialist pipeline. `role_roster` defaults to the
    standard roster; the task handler passes its own so the rendered capability
    catalog always reflects the roster actually in use. `failure_context` is
    non-empty only on a repair re-route (what a prior attempt was missing)."""
    roster = role_roster or build_default_role_roster()
    block = SpecialistRouterBlock(llm_adapter=llm_adapter)
    return await block.run(
        SpecialistRouterInput(
            block_id=block_id,
            agent_name="specialist_router",
            objective=f"Route the step '{step.objective}' to its specialist pipeline.",
            output_schema_name=_OUTPUT_SCHEMA_NAME,
            output_schema=_OUTPUT_SCHEMA,
            prompt_contract_name=SPECIALIST_ROUTER_V1,
            step=step,
            dependency_context=dependency_context,
            specialist_catalog=render_specialist_catalog(roster),
            failure_context=list(failure_context or []),
            llm_call_parameters=LLMCallParameters(
                thinking_enabled=False,
                reasoning_effort="low",
                timeout=_TIMEOUT_SECONDS,
                max_retries=1,
            ),
        )
    )


class PlanRouterInput(BaseReasoningBlockInput):
    steps: list[PlanStep] = Field(default_factory=list)
    specialist_catalog: str = ""


class PlanRouterOutput(BaseReasoningBlockOutput):
    routes: dict[str, list[RoutedSubStep]] = Field(default_factory=dict)


def _build_plan_user_prompt(block_input: PlanRouterInput) -> str:
    payload = {
        "steps": [
            {
                "step_id": step.step_id,
                "objective": step.objective,
                # The batch has not run, so there are no RESULTS to show -- but a
                # step's own declared dependencies are known at plan time, and are
                # the ids a sub-step must reference verbatim.
                "depends_on": list(step.depends_on),
                "success_criteria": list(step.success_criteria),
            }
            for step in block_input.steps
        ],
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class PlanRouterBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails OPEN to NO routes -- see `_fallback_output`."""

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_specialist_router_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(self, block_input: PlanRouterInput, telemetry: RunTelemetry) -> PlanRouterOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or SPECIALIST_PLAN_ROUTER_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)

        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract, block_input.specialist_catalog),
            user_prompt=_build_plan_user_prompt(block_input),
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
                return self._fallback_output(block_input, extra_warning="schema_validation_failed")
            normalized = repair_outcome.result

        return self._to_plan_output(normalized, block_input)

    def _to_plan_output(self, normalized: dict[str, Any], block_input: PlanRouterInput) -> PlanRouterOutput:
        raw_routes = normalized.get("routes")
        if not isinstance(raw_routes, list):
            return self._fallback_output(block_input, extra_warning="routes_not_a_list")

        known_ids = {step.step_id for step in block_input.steps}
        routes: dict[str, list[RoutedSubStep]] = {}
        for item in raw_routes:
            if not isinstance(item, dict):
                continue
            step_id = item.get("step_id")
            # A route naming a step the Planner never emitted is dropped, never
            # dispatched -- same posture as an invented specialist below.
            if not isinstance(step_id, str) or step_id not in known_ids:
                logger.warning("specialist_plan_router_dropped_unknown_step", extra={"stepId": step_id})
                continue
            pipeline: list[RoutedSubStep] = []
            for sub in item.get("pipeline") or []:
                if not isinstance(sub, dict):
                    continue
                try:
                    pipeline.append(RoutedSubStep.model_validate(sub))
                except Exception:  # noqa: BLE001 -- one bad sub-step must not sink the batch
                    logger.warning("specialist_plan_router_dropped_invalid_substep", extra={"stepId": step_id})
            # A step whose pipeline came back empty is simply left unrouted: the
            # task handler routes it itself, which is strictly better than
            # dispatching a fail-closed blind retrieval for it.
            if pipeline:
                routes[step_id] = pipeline

        return PlanRouterOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=1.0,
            routes=routes,
        )

    def _fallback_output(
        self, block_input: PlanRouterInput, *, extra_warning: str | None = None
    ) -> PlanRouterOutput:
        """Fails OPEN, unlike `SpecialistRouterBlock`'s fail-CLOSED single
        retrieval sub-step -- and deliberately so.

        This block is an OPTIMIZATION, not a dependency: every step it fails to
        route is routed by `route_step` at dispatch, exactly as before batching
        existed. So the safe failure is to return nothing and let the per-step
        router do its job -- guessing a blind retrieval pipeline here would
        replace a correct route with a wrong one to save a call.
        """
        warnings = ["specialist_plan_router_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return PlanRouterOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            routes={},
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> PlanRouterOutput:
        assert isinstance(block_input, PlanRouterInput)
        return self._fallback_output(block_input, extra_warning=f"reasoning_block_failed: {reason}")


async def route_plan(
    *,
    steps: list[PlanStep],
    llm_adapter: LLMAdapter,
    block_id: str,
    role_roster: dict[RoleName, RoleDefinition] | None = None,
) -> dict[str, list[RoutedSubStep]]:
    """Route a whole batch of plan steps in ONE call, keyed by step_id.

    Measured live (2026-07-15, ise_correctness): 24 of 25 routes were a
    one-element pipeline -- a single specialist label -- and each cost its own
    blocking LLM call before its step could start. `credits_remaining` alone
    paid 8 such calls across ~6 layers.

    What per-step routing buys that this cannot is `dependency_context`: the
    results a step's dependencies ACTUALLY produced, which a batch routed at
    plan time cannot see because nothing has run. On that same run, exactly one
    route used it -- reacting to a `degreeId` that failed to resolve, which was
    a get_entity bug since fixed. So the caller keeps that adaptation where it
    still pays: `run_task_handler` re-routes a step itself whenever its
    dependencies came back anything but clean.

    Returns `{}` on any failure -- an empty map means "nothing precomputed", and
    every step falls back to `route_step`. This function can only ever save
    calls; it can never be the reason a step is routed wrongly.
    """
    # A batch of one can only break even (one batch call replacing one per-step
    # call) -- and loses outright if the batch fails open, since the per-step
    # router then runs anyway. Nothing to win, so don't spend the call.
    if len(steps) <= 1:
        return {}
    roster = role_roster or build_default_role_roster()
    block = PlanRouterBlock(llm_adapter=llm_adapter)
    output = await block.run(
        PlanRouterInput(
            block_id=block_id,
            agent_name="specialist_plan_router",
            objective="Route every step of the plan to its specialist pipeline.",
            output_schema_name=_PLAN_OUTPUT_SCHEMA_NAME,
            output_schema=_PLAN_OUTPUT_SCHEMA,
            prompt_contract_name=SPECIALIST_PLAN_ROUTER_V1,
            steps=list(steps),
            specialist_catalog=render_specialist_catalog(roster),
            llm_call_parameters=LLMCallParameters(
                thinking_enabled=False,
                reasoning_effort="low",
                # Scaled off the per-step bound: this call does the work of N of
                # them, so it must not be held to one step's budget.
                timeout=_PLAN_TIMEOUT_SECONDS,
                max_retries=1,
            ),
        )
    )
    return dict(output.routes)


__all__ = [
    "SPECIALIST_ROUTER_V1",
    "SPECIALIST_PLAN_ROUTER_V1",
    "RoutedSubStep",
    "SpecialistRouterOutput",
    "SpecialistRouterInput",
    "SpecialistRouterBlock",
    "PlanRouterInput",
    "PlanRouterOutput",
    "PlanRouterBlock",
    "route_step",
    "route_plan",
    "build_specialist_router_prompt_registry",
]
