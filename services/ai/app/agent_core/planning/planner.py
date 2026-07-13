"""Adaptive Planner (docs/agent/AGENT_VISION.md §3, §3.1): invoked
repeatedly, each time producing only the next runnable chunk of steps --
never a full, upfront plan.

Runs on `BaseReasoningBlock` (docs/agent/PLANNER_OUTPUT_DESIGN.md +
follow-on reasoning-block design discussion), the same foundation Request
Understanding already migrated to -- single-shot, its own typed
Input/Output, its own prompt contract. Diverges from Request Understanding's
own shape in two deliberate ways: raw and final output stay separate types
(the rewrite pipeline in `planning/rewrite.py` needs external state --
invocation number, known global ids -- that isn't derivable from the LLM's
own response the way RU's hollow-checks are), and failure resolves to
`blocked_needs_clarification`, not an inert pass-through -- a fabricated
`next_steps` would be a dispatchable action against real state.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.agent_core.planning.rewrite import check_hollow_result, compute_plan_graph, rewrite_step_ids
from app.agent_core.planning.schemas import (
    PlannerInvocationInput,
    PlannerInvocationOutput,
    PlannerReasoningBlockInput,
    PlannerReasoningBlockOutput,
    PlanStepDraft,
)
from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, LLMCallParameters

logger = logging.getLogger(__name__)

PLANNER_V1 = "planner_v1"

# A distinct contract, not a distinct code path -- registered alongside
# planner_v1 in the same registry and run through the exact same
# PlannerReasoningBlock. Used by orchestrator/task_handler.py when it
# recursively decomposes a single, too-complex PlanStep into its own
# private sub-plan: the role_prompt below frames that context correctly
# ("decomposing one internal step of a larger plan") instead of planner_v1's
# own framing ("the student's request"), which would otherwise be actively
# misleading for a nested invocation.
NESTED_PLANNER_V1 = "planner_nested_v1"

PLANNER_OUTPUT_SCHEMA_NAME = "planner_invocation_output_v1"

_PLAN_STEP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "step_id": {"type": "string"},
        "objective": {"type": "string"},
        "depends_on": {"type": "array", "items": {"type": "string"}},
        "success_criteria": {"type": "array", "items": {"type": "string"}},
        "assumptions_to_verify": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["step_id", "objective"],
    "additionalProperties": False,
}

PLANNER_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_status": {"type": "string", "enum": ["in_progress", "complete", "blocked_needs_clarification"]},
        "next_steps": {"type": "array", "items": _PLAN_STEP_SCHEMA},
        "plan_summary": {"type": "string"},
        "clarification_question": {"type": ["string", "null"]},
    },
    "required": ["plan_status", "plan_summary"],
    "additionalProperties": False,
}

_FALLBACK_CLARIFICATION = (
    "I wasn't able to determine how to proceed with this request. Could you rephrase it or provide more detail?"
)

_MAX_SCHEMA_REPAIR_ATTEMPTS = 2

# The Planner's own request-level bound (LLMCallParameters.timeout/
# max_retries, threaded through BaseReasoningBlock -> build_chat_llm's
# now-widened client cache key) -- set here, on this component's own input,
# never globally, so it can never affect Request Understanding's or any
# other component's calls. 60s gives real headroom over what
# thinking_enabled=True + reasoning_effort="medium" calls have actually
# taken in live-eval runs so far (observed well under 30s per call) while
# still bounding a genuine hang; max_retries=2 makes explicit what the
# underlying SDK already defaults to, rather than leaving it implicit.
_TIMEOUT_SECONDS = 60.0
_MAX_RETRIES = 2


def _planner_contract() -> PromptContract:
    return PromptContract(
        name=PLANNER_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Planner for the UniPilot Agent, a Technion academic advising assistant. "
            "You are invoked repeatedly over the course of one turn. Each time, given Request "
            "Understanding's structured breakdown of the student's request plus everything the plan "
            "has accumulated so far, your one job is to produce the NEXT batch of runnable work "
            "steps -- never a full upfront plan, and never more than what is genuinely fully "
            "knowable right now."
        ),
        instructions=[
            "step_id is a simple local label for THIS batch only -- use short letters like 'A', "
            "'B', 'C'. When a step depends on another step in this SAME batch, reference that "
            "step's local label in depends_on. When a step depends on a step that already exists "
            "in plan_graph_so_far or state_index (already completed in a prior round), reference "
            "that step's EXACT existing id from plan_graph_so_far/state_index -- never invent a new "
            "local label for something that already exists.",
            "depends_on must be complete, not approximate. Leaving out a real dependency is far "
            "worse than including an extra one: a missing dependency can never be recovered later, "
            "so whenever a step's objective genuinely needs a fact another step produces, declare "
            "it as a dependency, even if you are not fully certain.",
            "Plan every sub_ask in sub_asks jointly, in this one pass -- never as independent, "
            "separately-planned sub-plans. Sub-asks routinely share underlying facts (e.g. two "
            "different concerns might both need the student's completed-course record); planning "
            "them separately would duplicate steps that fetch the same fact twice. If two sub_asks "
            "need the same fact, produce exactly one step for it and let both downstream steps "
            "depend on it.",
            "constraints are not steps of their own. Thread each constraint into whichever step's "
            "objective it actually bears on -- never attach a constraint indiscriminately to every "
            "step in the batch.",
            "For each item in open_questions, either proceed with a stated, explicit assumption "
            "(recorded in that step's assumptions_to_verify so it is auditable, not silently "
            "assumed), or, if the ambiguity is genuinely blocking, set "
            "plan_status='blocked_needs_clarification' and ask a real, specific question in "
            "clarification_question. Never silently guess past a genuine ambiguity, and never set "
            "blocked_needs_clarification without a real question to ask.",
            "confidence reflects how certain Request Understanding was about this request. When "
            "confidence is low, that is a legitimate reason to schedule a resolving or verifying "
            "step EARLY in this batch, before committing to a long chain of steps that depend on a "
            "shaky premise.",
            "implies_action_request=true means the student is asking you to perform or record a "
            "real state change on their behalf. The plan must end in, or include, a step that "
            "PROPOSES that action for confirmation -- never conclude the plan by treating the "
            "state-changing action as already performed.",
            "Produce every step that is currently fully and correctly specifiable, given only what "
            "is already known -- this may be many steps or few, but do not artificially shrink the "
            "batch, and do not include a step whose correct shape depends on a result you do not "
            "have yet. What must wait for a later round is only whatever step's SHAPE (not just its "
            "timing) genuinely depends on something that doesn't exist yet.",
            "When a step needs 'the current semester', 'next semester', or any other fact "
            "relative to today's date, scope it as a single Retrieval step calling the "
            "get_current_semester tool directly -- never as a Retrieval step for 'today's "
            "date' followed by a separate Calculation step to work out the semester from it. "
            "apply_deterministic_rule has no date-range rule type, so a Calculation step given "
            "only a raw date can never reliably determine which semester it falls into.",
            "A hypothetical or 'what if' framed request (e.g. 'what happens if I fail/drop X') "
            "almost always needs the student's own current academic state (completed courses, "
            "current plan, GPA, standing) fetched as one of the very first steps, in addition to "
            "whatever policy or course facts are needed -- that state is required regardless of "
            "what the other facts turn out to say, so it belongs in this round, not deferred.",
            "If a step's objective can already be fully and precisely written now -- even though it "
            "depends on results other steps in this SAME batch will produce -- include it in this "
            "batch too, with the appropriate depends_on. Only wait for a later round when the "
            "step's own SHAPE, not just its result, genuinely cannot be determined yet. For "
            "example, once you know two steps will each retrieve a list (e.g. required courses and "
            "completed courses), a step that computes or compares across both lists can usually be "
            "specified now, in this same batch, rather than deferred to the round after next. This "
            "applies just as much to a single-value comparison: once you know one step will retrieve "
            "a value (e.g. a GPA, a credit count, a number of semesters remaining) and another step "
            "will retrieve a threshold or limit to compare it against (e.g. a probation GPA "
            "threshold, a credit requirement, a program's semester limit), include the comparison "
            "step in this same batch too -- do not stop at fetching the two facts and defer the "
            "comparison itself to a later round.",
            "Never produce branching or conditional structure inside one batch (e.g. 'if step A "
            "shows X, do step B, else do step C'). Adaptivity happens across separate invocations, "
            "reacting to real results -- never as an explicit branch inside one output.",
            "Write each step's objective precisely enough that a reader could tell, from the text "
            "alone, what KIND of work it is (looking something up, interpreting/explaining a "
            "result, validating a calculation, exploring a hypothetical, or composing a final "
            "answer) without needing any other field to disambiguate.",
            "A course's or program's REQUIREMENT-FULFILLMENT status (e.g. mandatory, elective, "
            "core, which track/degree requirement it satisfies) is a fact that lives in prose "
            "describing degree/track requirements, not a structured graph attribute -- it requires "
            "reading and interpreting that text, unlike a course's code, credit count, or "
            "prerequisite list, which are structured lookups. Never bundle a requirement-fulfillment "
            "classification into the same step as a purely structural catalog fetch; give it its "
            "own separate step instead.",
            "A student's cumulative GPA, semester GPA, or academic-standing/probation status is a "
            "DERIVED fact computed from raw per-course grades and credit weights against a policy "
            "threshold -- never assume it is a field a Retrieval fetch can simply return. A step "
            "asking for it must either be scoped as 'fetch the raw per-course grades and credits' "
            "(a Retrieval-shaped fetch) or, when a derived value/status is genuinely required, "
            "include a separate step that applies the relevant rule to those raw facts "
            "(a Calculation/apply_deterministic_rule step) -- never one step that expects a bare "
            "fetch to return an already-computed GPA or standing label.",
            "A requirement-fulfillment status is always relative to ONE specific degree program or "
            "track -- the same course can be mandatory in one program and elective in another -- so "
            "it can never be resolved without knowing which program applies. If any step in this "
            "same batch, plan_graph_so_far, or state_index fetches (or will fetch) the student's "
            "declared degree program, the requirement-fulfillment step MUST declare that step as a "
            "dependency. If no such step exists anywhere yet, add one to this batch and depend on "
            "it, rather than leaving the requirement-fulfillment step to discover the missing "
            "program on its own later.",
            "A degree/track's total-credit requirement (or any other specific number or rule that "
            "lives only in that program's wiki-page prose, not a structured graph attribute) cannot "
            "be produced by a bare Retrieval fetch of the program -- fetching a program/track entity "
            "returns prose text, not a structured field. Extracting a specific number or rule from "
            "that text needs its own separate Interpretation step (interpret_text), exactly like a "
            "requirement-fulfillment classification above. When a step needs 'how many credits "
            "remain', schedule: a Retrieval step for the student's own completed credits, an "
            "Interpretation step to extract the program's total-credit requirement from its wiki "
            "page, and a Calculation step comparing the two -- never a single Retrieval step expected "
            "to return the remaining-credits count directly.",
            "A single retrieval of one entity (e.g. get_entity on a student_profile, a course, a "
            "program) returns that entity's ENTIRE record as one document -- every field on it "
            "comes back together in one call. A student's degree program, year of study, academic "
            "standing, and faculty are all fields on the ONE student_profile document, not separate "
            "facts; a course's code, credit count, and prerequisite list are all fields on the ONE "
            "course document. When this batch needs several such fields from the same entity, "
            "produce exactly ONE retrieval step for that entity and let every downstream step that "
            "needs one of its fields declare THAT single step as its dependency -- never a separate "
            "step per field of the same record. (This does not apply to a field that is itself "
            "DERIVED via interpretation or calculation, e.g. GPA/standing computed from raw grades, "
            "or a requirement-fulfillment classification read from prose -- those still get their "
            "own step per the instructions above; only genuinely structural fields of the same "
            "record collapse into one step.)",
            "success_criteria and assumptions_to_verify must be concrete and checkable -- specific "
            "facts or conditions that can be verified true or false against the step's actual "
            "result, never a vague hedge like 'gather relevant information'.",
            "plan_status is always explicit: 'in_progress' when there is more work after this "
            "batch, 'complete' when this batch is the last one needed to answer the request, "
            "'blocked_needs_clarification' when a genuine ambiguity blocks proceeding. Never leave "
            "it to be inferred from next_steps being empty.",
            "If state_index/plan_graph_so_far already shows a fact was fetched and came back "
            "explicitly null/absent from an authoritative source (e.g. the student's own profile has "
            "no declared degree program or track), that fact is CONCLUSIVELY known to be absent, not "
            "merely unfound -- never schedule another step that re-fetches the same record or "
            "searches elsewhere trying to re-derive it; that step cannot succeed and only burns the "
            "planning budget. Either proceed using the absence itself as a known fact (e.g. compose an "
            "answer that says the student has not yet declared a program), or, only if the missing "
            "fact is genuinely required and cannot be substituted, set "
            "plan_status='blocked_needs_clarification' and ask the student for it directly.",
            "If state_index shows a prior step already failed and its warnings indicate a search/lookup "
            "came back empty after being tried, or that no tool exists to perform an implied action, "
            "do not schedule another step that retries a cosmetically different phrasing of the same "
            "search or another approach to the same unperformable action -- that evidence should "
            "instead flow into the final answer (state what wasn't found, or that the action can't "
            "be performed) or a clarification question, never a silent retry loop. The same applies "
            "when a prior search came back not empty but AMBIGUOUS -- several genuinely distinct "
            "candidates with no clearly-dominant match (e.g. multiple same-named courses/tracks whose "
            "relevance scores cluster close together) -- retrying with a rephrased query will not "
            "resolve a genuine multi-way tie; set plan_status='blocked_needs_clarification' and ask "
            "the student to disambiguate, listing the real candidates found, rather than spending "
            "further steps trying different search phrasings against the same ambiguous result set.",
            "When implies_action_request=true, the step that proposes/declines the action for "
            "confirmation does not need to wait for every referenced entity to be fully resolved "
            "first -- if resolving a referenced entity (a course name, a degree program) is proving "
            "difficult (see state_index for prior failed attempts per the instruction above), schedule "
            "the proposal/decline step early using whatever has been resolved so far, rather than "
            "exhausting the exploration budget on ambiguous entity resolution before addressing the "
            "action request at all.",
            "If `unresolvable_entities` in your input lists a specific entity name or search query "
            "that has already been tried and came back empty within this turn, do not schedule "
            "another step that searches for the same entity or a trivially rephrased variant of it "
            "-- that search has been conclusively tried and will not succeed on retry. Use the "
            "absence itself as a known fact (e.g. state that the entity could not be found in the "
            "catalog), or, only if the missing entity is genuinely required and cannot be "
            "substituted, set plan_status='blocked_needs_clarification'.",
        ],
        allowed_context_fields=None,
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        default_risk_level="high",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.1,
        safety_rules=[
            "Do not expose chain-of-thought, hidden reasoning, or private notes.",
            "Do not fabricate a completed action -- a state-changing action is only ever proposed, "
            "never described as already done.",
        ],
    )


def _planner_nested_contract() -> PromptContract:
    """Same instructions/safety_rules/schema as planner_v1, verbatim --
    only `name` and `role_prompt` differ. One structured decision (the
    Planner's own instructions for depends_on completeness, batching,
    open_questions handling, etc.) should never fork into two independently
    drifting copies; `.model_copy` guarantees that."""
    base = _planner_contract()
    return base.model_copy(
        update={
            "name": NESTED_PLANNER_V1,
            "role_prompt": (
                "You are the Planner for the UniPilot Agent, a Technion academic advising assistant. "
                "You are being invoked by a task handler to decompose ONE internal step of a larger "
                "plan -- not a fresh user turn. `user_goal` here is that one step's own objective, "
                "not the student's original request; `original_user_message` is passed through only "
                "for tone/language grounding. You are invoked repeatedly over the course of resolving "
                "this one step. Each time, given that step's objective plus everything this private "
                "sub-plan has accumulated so far, your one job is to produce the NEXT batch of "
                "runnable work steps needed to fully resolve it -- never a full upfront plan, and "
                "never more than what is genuinely fully knowable right now."
            ),
        }
    )


def build_planner_prompt_registry() -> PromptRegistry:
    """The two generic contracts plus this layer's own -- mirrors
    `request_understanding.build_request_understanding_prompt_registry()`'s pattern."""
    registry = build_default_prompt_registry()
    registry.register(_planner_contract())
    registry.register(_planner_nested_contract())
    return registry


def _build_system_prompt(contract: PromptContract) -> str:
    lines = [contract.role_prompt]
    if contract.instructions:
        lines.append("")
        lines.append("INSTRUCTIONS:")
        lines.extend(f"- {item}" for item in contract.instructions)
    if contract.safety_rules:
        lines.append("")
        lines.append("SAFETY RULES:")
        lines.extend(f"- {item}" for item in contract.safety_rules)
    return "\n".join(lines).strip()


def _build_user_prompt(block_input: PlannerReasoningBlockInput) -> str:
    payload = {
        "objective": block_input.objective,
        "planner_input": block_input.planner_input.model_dump(),
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class PlannerReasoningBlock(BaseReasoningBlock):
    """Single-shot, no tools. Fails CLOSED, not open -- unlike Request
    Understanding's inert fail-open pass-through, a fabricated `next_steps`
    is a dispatchable action against real state, so any failure resolves to
    `blocked_needs_clarification` plus a real question, never a guess.
    """

    def __init__(
        self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry | None = None, **kwargs: Any
    ) -> None:
        super().__init__(
            llm_adapter=llm_adapter,
            prompt_registry=prompt_registry or build_planner_prompt_registry(),
            **kwargs,
        )

    async def _run_internal(
        self, block_input: PlannerReasoningBlockInput, telemetry: RunTelemetry
    ) -> PlannerReasoningBlockOutput:
        contract = self._resolve_prompt_contract(block_input.prompt_contract_name or PLANNER_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        user_prompt = _build_user_prompt(block_input)

        # `LLMAdapterError` here is intentionally left uncaught -- it
        # propagates to `run()`'s outer "never raises" wrapper, which calls
        # `_failed_output` below. Keeps the fail-closed fallback in one place.
        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=user_prompt,
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
        self, normalized: dict[str, Any], block_input: PlannerReasoningBlockInput
    ) -> PlannerReasoningBlockOutput:
        plan_status = normalized.get("plan_status", "blocked_needs_clarification")
        plan_summary = str(normalized.get("plan_summary") or "")
        clarification_question = normalized.get("clarification_question")
        try:
            drafts = [PlanStepDraft.model_validate(step) for step in (normalized.get("next_steps") or [])]
        except Exception:  # noqa: BLE001 -- a malformed step must not crash the block
            logger.exception("planner_next_steps_invalid")
            return self._fallback_output(block_input, extra_warning="next_steps_invalid")

        # Moved in from the old wrapper-function version of this check: it
        # only needs plan_status/next_steps/clarification_question, all
        # present in the LLM's own response -- the rewrite pass never drops
        # whole steps (only edges), so this check is equally valid on the
        # raw drafts as on the rewritten PlanSteps.
        if check_hollow_result(plan_status, drafts, clarification_question):
            return self._fallback_output(block_input, extra_warning="hollow_result")

        try:
            confidence = float(normalized.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        return PlannerReasoningBlockOutput(
            status="completed",
            schema_valid=True,
            result=normalized,
            confidence=confidence,
            plan_status=plan_status,
            plan_summary=plan_summary,
            clarification_question=clarification_question,
            next_steps=drafts,
        )

    def _fallback_output(
        self, block_input: PlannerReasoningBlockInput, *, extra_warning: str | None = None
    ) -> PlannerReasoningBlockOutput:
        """The one fail-CLOSED result every failure path resolves to: ask
        for clarification rather than dispatch a guessed or fabricated
        plan. `status="completed"` (not "failed") -- a well-formed "must
        ask" result is a valid, actionable output for the Orchestrator,
        mirroring RU's own choice for its fail-open fallback.
        """
        warnings = ["planner_fallback_used"]
        if extra_warning:
            warnings.append(extra_warning)
        return PlannerReasoningBlockOutput(
            status="completed",
            schema_valid=False,
            result=None,
            confidence=0.0,
            warnings=warnings,
            plan_status="blocked_needs_clarification",
            plan_summary="Planner reasoning unavailable or failed; no steps could be produced.",
            clarification_question=_FALLBACK_CLARIFICATION,
            next_steps=[],
        )

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> PlannerReasoningBlockOutput:
        """Overridden: called by `run()`'s outer wrapper when `_run_internal`
        raises. A raised exception must fail closed too, not just return a
        bare `status="failed"`."""
        assert isinstance(block_input, PlannerReasoningBlockInput)
        return self._fallback_output(block_input, extra_warning=f"reasoning_block_failed: {reason}")


async def build_next_plan_steps(
    *,
    planner_input: PlannerInvocationInput,
    llm_adapter: LLMAdapter,
    block_id: str,
    invocation: int,
    prompt_contract_name: str = PLANNER_V1,
    thinking_enabled: bool | None = None,
    reasoning_effort: str | None = None,
    timeout: float | None = None,
) -> PlannerInvocationOutput:
    block = PlannerReasoningBlock(llm_adapter=llm_adapter)
    block_output = await block.run(
        PlannerReasoningBlockInput(
            block_id=block_id,
            agent_name="planner",
            objective=planner_input.user_goal,
            output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
            output_schema=PLANNER_OUTPUT_SCHEMA,
            prompt_contract_name=prompt_contract_name,
            planner_input=planner_input,
            # Explicitly requested, unlike Request Understanding (which
            # defers to the adapter's global default): dependency-
            # completeness is real multi-step inference, not classification,
            # and under-declaring a dependency is unrecoverable downstream.
            # Set here on the input, not the contract -- PromptContract has
            # no reasoning_effort/thinking_enabled field; only `temperature`
            # has a contract-level default (see reasoning_blocks/base.py's
            # `_resolve_llm_call_parameters`).
            llm_call_parameters=LLMCallParameters(
                thinking_enabled=thinking_enabled if thinking_enabled is not None else True,
                reasoning_effort=reasoning_effort if reasoning_effort is not None else "medium",
                timeout=timeout if timeout is not None else _TIMEOUT_SECONDS,
                max_retries=_MAX_RETRIES,
            ),
        )
    )

    next_steps = rewrite_step_ids(
        block_output.next_steps,
        invocation=invocation,
        known_global_ids=set(planner_input.plan_graph_so_far.forward.keys()),
    )

    return PlannerInvocationOutput(
        plan_status=block_output.plan_status,
        next_steps=next_steps,
        plan_summary=block_output.plan_summary,
        clarification_question=block_output.clarification_question,
        plan_graph=compute_plan_graph(next_steps),
    )


__all__ = [
    "PLANNER_V1",
    "NESTED_PLANNER_V1",
    "PLANNER_OUTPUT_SCHEMA_NAME",
    "PLANNER_OUTPUT_SCHEMA",
    "PlannerReasoningBlock",
    "build_planner_prompt_registry",
    "build_next_plan_steps",
]
