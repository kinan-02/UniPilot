"""Planner Council -- a latency-bounded, critic-based replacement for the
Planner's single thinking-enabled call.

Why this exists (found via live-eval): the old Planner made ONE
`thinking_enabled=True` call with a 60s timeout. For a high-complexity
request the model could not finish reasoning inside 60s, the call timed out,
retried, timed out again, and the WHOLE turn produced no plan at all -- one
slow call = total loss. Making the single call "think harder" only makes
that worse under a hard 300s turn budget.

The council trades that one fragile call for a small pipeline of FAST,
no-thinking calls, each individually reliable:

    draft ─┬─ coverage critic ─┐
           ├─ grounding critic ─┼─→ synthesize → revised plan
           └─ criteria  critic ─┘   (only if critics found issues)

- Drafter: the existing `PlannerReasoningBlock` run with fast params
  (no thinking, low effort) -- produces a candidate batch quickly.
- Critics: run IN PARALLEL (same wall-clock as one call), each checking the
  draft against ONE failure mode we actually observed live -- missing
  coverage, hallucinated/ungrounded references, and gold-plated or
  unsatisfiable success_criteria. A critic that fails or times out simply
  contributes no findings (degrade, never block).
- Synthesizer: only runs if some critic flagged a real issue; revises the
  draft to fix them. If it fails, the already-valid draft is returned.

Every member is bounded and no-thinking, so the whole council is a handful
of fast calls with a guaranteed floor: if the drafter itself fails, the
draft's own fail-closed `blocked_needs_clarification` output is returned, so
a turn never silently gets zero output.

Returns a `PlannerReasoningBlockOutput` -- the exact type
`PlannerReasoningBlock.run()` returns -- so `build_next_plan_steps` swaps one
for the other with no change to the rewrite/graph pipeline or any caller.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from app.agent_core.planning.planner import (
    PLANNER_OUTPUT_SCHEMA_NAME,
    PLANNER_V1,
    PlannerReasoningBlock,
    PlannerReasoningBlockOutput,
    _build_system_prompt,
)
from app.agent_core.planning.rewrite import check_hollow_result
from app.agent_core.planning.schemas import (
    PlannerInvocationInput,
    PlannerReasoningBlockInput,
    PlanStepDraft,
)
from app.agent_core.reasoning.grounding import build_shared_grounding_block
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning.prompt_registry import PromptContract, PromptRegistry, build_default_prompt_registry
from app.agent_core.reasoning_blocks.base import BaseReasoningBlock, RunTelemetry
from app.agent_core.reasoning_blocks.schemas import BaseReasoningBlockInput, BaseReasoningBlockOutput, LLMCallParameters

logger = logging.getLogger(__name__)

# All council members are fast + no-thinking. These bounds are deliberately
# generous enough to succeed but far short of the old 60s-thinking call that
# was timing out; three sequential fast phases (draft -> critics(parallel) ->
# synth) still fit comfortably inside a single Planner invocation's share of
# the 300s turn budget.
_DRAFTER_TIMEOUT = 30.0
_CRITIC_TIMEOUT = 25.0
_SYNTH_TIMEOUT = 30.0
_MAX_SCHEMA_REPAIR_ATTEMPTS = 1

COVERAGE_CRITIC_V1 = "planner_coverage_critic_v1"
GROUNDING_CRITIC_V1 = "planner_grounding_critic_v1"
CRITERIA_CRITIC_V1 = "planner_criteria_critic_v1"
PARSIMONY_CRITIC_V1 = "planner_parsimony_critic_v1"
STRATEGY_CRITIC_V1 = "planner_strategy_critic_v1"
DOMAIN_CRITIC_V1 = "planner_domain_critic_v1"
SYNTHESIZER_V1 = "planner_synthesizer_v1"

_CRITIC_OUTPUT_SCHEMA_NAME = "planner_critic_output_v1"
_CRITIC_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        # Each issue is one concrete, actionable sentence naming the step
        # (by its local step_id) and what to change -- never vague praise.
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["issues"],
    "additionalProperties": False,
}

_DEFAULT_CRITICS: tuple[str, ...] = (
    COVERAGE_CRITIC_V1,
    GROUNDING_CRITIC_V1,
    CRITERIA_CRITIC_V1,
    PARSIMONY_CRITIC_V1,
)


# ── Contracts ──────────────────────────────────────────────────────────────


def _coverage_critic_contract() -> PromptContract:
    return PromptContract(
        name=COVERAGE_CRITIC_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Coverage Critic on the UniPilot Planner's review council. You are given "
            "the student's structured request and a DRAFT batch of plan steps. Your ONE job: find "
            "gaps in coverage and dependencies -- nothing else."
        ),
        instructions=[
            "Report only concrete, actionable issues. Each issue names the specific gap and, where "
            "relevant, the step_id it concerns. If the draft is fully adequate, return an empty list.",
            "Check every sub_ask is addressed by some step. A sub_ask with no step covering it is an "
            "issue: name the missing step.",
            "Check depends_on is complete: if a step's objective needs a fact another step produces "
            "but doesn't declare it in depends_on, that is an issue (a missing dependency is "
            "unrecoverable downstream).",
            "Do NOT invent extra work. Suggesting a step the request doesn't need is itself a defect "
            "-- flag only genuinely missing coverage, never nice-to-haves.",
        ],
        allowed_context_fields=None,
        output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def _grounding_critic_contract() -> PromptContract:
    return PromptContract(
        name=GROUNDING_CRITIC_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Grounding Critic on the UniPilot Planner's review council. You are given "
            "the student's structured request and a DRAFT batch of plan steps. Your ONE job: catch "
            "any step that references data, fields, or tools that do not actually exist -- nothing else."
        ),
        instructions=[
            "Report only concrete, actionable issues, each naming the step_id and the ungrounded "
            "reference. If everything is grounded, return an empty list.",
            "Flag any success_criterion or objective that demands a student_profile field which does "
            "not exist (e.g. year_of_study, declared_tracks, degree_program, cumulative_credits_earned "
            "are NOT real fields -- see the entity-shape section above). Such a criterion can never be "
            "satisfied and will loop until timeout.",
            "Flag any step that expects a value no tool can produce -- e.g. converting a semester "
            "label into a YYYY-S code with a calculation step (get_current_semester already returns "
            "the code; nothing else can compute it).",
            "Do not flag genuinely grounded references. Uncertainty about whether a course code exists "
            "is fine to note as a low-priority issue, but real profile fields and real tools are not "
            "defects.",
        ],
        allowed_context_fields=None,
        output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def _criteria_critic_contract() -> PromptContract:
    return PromptContract(
        name=CRITERIA_CRITIC_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Criteria Critic on the UniPilot Planner's review council. You are given the "
            "student's structured request and a DRAFT batch of plan steps. Your ONE job: make each "
            "step's success_criteria the MINIMUM needed for its result to be usable -- nothing else."
        ),
        instructions=[
            "Report only concrete, actionable issues, each naming the step_id and the over-strict or "
            "unsatisfiable criterion. If all criteria are already minimal and satisfiable, return an "
            "empty list.",
            "Flag gold-plated criteria: demands for exact textual citations, specific section numbers, "
            "a particular output format, or exhaustive completeness that the student's actual question "
            "does not require. A downstream check enforces success_criteria literally, so an over-strict "
            "criterion triggers wasteful re-planning even when the step's result already answers the need.",
            "Flag criteria a result can only satisfy by chance of formatting rather than content (e.g. "
            "'returned EXACTLY as YYYY-S') -- prefer 'includes the semester code' over 'exactly as'.",
            "A criterion should capture the essential fact the step must produce, not how prettily it is "
            "packaged. Do not weaken a criterion so far that a wrong or missing result would pass.",
        ],
        allowed_context_fields=None,
        output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def _parsimony_critic_contract() -> PromptContract:
    return PromptContract(
        name=PARSIMONY_CRITIC_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Parsimony Critic on the UniPilot Planner's review council. You are given "
            "the student's structured request and a DRAFT batch of plan steps. Your ONE job: catch "
            "REDUNDANCY and OVER-DECOMPOSITION -- steps that should be merged, removed, or made to "
            "depend on an existing result instead of redoing it -- nothing else. A tight plan runs "
            "far cheaper: every extra step becomes its own dispatch + verification downstream."
        ),
        instructions=[
            "Report only concrete, actionable issues, each naming the step_ids involved and the "
            "merge/removal. If the plan is already tight, return an empty list.",
            "Flag two or more steps that fetch or produce the SAME fact (e.g. two steps that both "
            "retrieve the student's profile, or both look up the same course) -- there must be "
            "exactly ONE step per fact, with everything else depending on it.",
            "Flag over-decomposition of one entity's structural fields: a student_profile's degree "
            "program, year, standing, and faculty all come back in ONE get_entity call, and a "
            "course's code, credits, and prerequisites in one -- splitting those across separate "
            "retrieval steps is waste; merge them into a single step the others depend on. (A "
            "DERIVED value like GPA/standing, or a requirement-fulfillment classification read from "
            "prose, legitimately gets its own step -- never flag those.)",
            "Flag any step that redoes work already present in plan_graph_so_far or state_index -- "
            "it should reference that existing id as a dependency, not recompute the result.",
            "Do NOT remove coverage. When unsure whether two steps are genuinely the same, leave "
            "them -- merging away a needed step is worse than an extra one. Never propose a merge "
            "that would combine two DIFFERENT kinds of work (a fetch and a derivation) into one step.",
        ],
        allowed_context_fields=None,
        output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def _strategy_critic_contract() -> PromptContract:
    return PromptContract(
        name=STRATEGY_CRITIC_V1,
        version="1.0.0",
        role_prompt=(
            "You are the Strategy Critic on the UniPilot Planner's review council. You are given the "
            "student's structured request and a DRAFT batch of plan steps. Your ONE job: challenge the "
            "high-level APPROACH -- is there a materially simpler or more direct way to answer the actual "
            "question, or is the plan solving the wrong subproblem? -- nothing else. The critics are "
            "anchored to the drafter's first idea; you are the deliberate counterweight to that anchoring."
        ),
        instructions=[
            "Report only concrete, actionable issues, each naming the step_ids and the simpler/different "
            "approach. If the strategy is already the most direct one that answers the request, return an "
            "empty list.",
            "Flag over-planning: a multi-step retrieval-and-analysis chain where the question could be "
            "answered by one or two steps. Name the steps that collapse and what replaces them.",
            "Flag solving the wrong subproblem: steps that answer a related-but-different question than the "
            "student actually asked, or that chase detail the request never needed.",
            "Do NOT propose ADDING work to look thorough, and do NOT rewrite a sound plan for style. A "
            "different approach is an issue only when it is genuinely simpler or more correct, not merely "
            "another way to do the same thing.",
        ],
        allowed_context_fields=None,
        output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def _domain_critic_contract() -> PromptContract:
    return PromptContract(
        name=DOMAIN_CRITIC_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Domain Critic on the UniPilot Planner's review council. You are given the "
            "student's structured request and a DRAFT batch of plan steps. Your ONE job: catch plans that "
            "get Technion ACADEMIC REASONING wrong -- prerequisite, credit, degree-rule, and semester "
            "semantics -- nothing else."
        ),
        instructions=[
            "Report only concrete, actionable issues, each naming the step_id and the academic-reasoning "
            "mistake. If the plan is academically sound, return an empty list.",
            "Flag eligibility/prerequisite checks that do not evaluate the target course's ACTUAL "
            "prerequisite rules against the student's ACTUAL completed courses -- e.g. a plan that judges "
            "eligibility without retrieving one of those two, or that assumes a prerequisite is met.",
            "Flag credit / degree-rule reasoning that ignores requirement buckets or catalog-version "
            "consistency (a rule must come from the same catalog the student is bound to), and "
            "semester-availability claims not grounded in when the course is actually offered.",
            "Do NOT invent extra academic checks the question does not need, and do not flag a correct "
            "simplification. Flag only reasoning that would produce a wrong or unsafe academic answer.",
        ],
        allowed_context_fields=None,
        output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.0,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def _synthesizer_contract() -> PromptContract:
    return PromptContract(
        name=SYNTHESIZER_V1,
        version="1.0.0",
        role_prompt=(
            f"{build_shared_grounding_block()}\n\n"
            "You are the Synthesizer on the UniPilot Planner's review council. You are given the "
            "student's structured request, a DRAFT batch of plan steps, and a list of issues the "
            "critics found. Produce a REVISED batch that fixes those issues while preserving "
            "everything the draft already got right."
        ),
        instructions=[
            "Fix every issue the critics raised, and change nothing else -- keep the draft's correct "
            "steps, ids, and dependencies intact. This is a revision, not a fresh plan.",
            "Never add a step just to look thorough. If the critics asked for a missing step, add "
            "exactly that; otherwise keep the step count as-is or smaller.",
            "Keep each success_criterion the minimum that makes the step's result usable -- do not "
            "reintroduce gold-plated citation/format/completeness demands.",
            "Output the SAME schema the draft used: plan_status, plan_summary, next_steps (each with "
            "step_id, objective, depends_on, success_criteria, assumptions_to_verify), and "
            "clarification_question only when genuinely blocked.",
            "step_id labels stay simple local letters ('A', 'B', ...); a depends_on entry referencing "
            "an already-existing step keeps that step's exact id.",
        ],
        allowed_context_fields=None,
        output_schema_name=PLANNER_OUTPUT_SCHEMA_NAME,
        default_risk_level="low",
        default_min_iterations=1,
        default_max_iterations=1,
        default_temperature=0.1,
        safety_rules=["Do not expose chain-of-thought, hidden reasoning, or private notes."],
    )


def build_council_prompt_registry() -> PromptRegistry:
    registry = build_default_prompt_registry()
    registry.register(_coverage_critic_contract())
    registry.register(_grounding_critic_contract())
    registry.register(_criteria_critic_contract())
    registry.register(_parsimony_critic_contract())
    registry.register(_strategy_critic_contract())
    registry.register(_domain_critic_contract())
    registry.register(_synthesizer_contract())
    return registry


# ── Inputs / Outputs ────────────────────────────────────────────────────────


class _CriticInput(BaseReasoningBlockInput):
    planner_input: PlannerInvocationInput
    draft_steps: list[dict[str, Any]]
    plan_summary: str = ""


class _CriticOutput(BaseReasoningBlockOutput):
    issues: list[str] = []


class _SynthesizerInput(PlannerReasoningBlockInput):
    draft_steps: list[dict[str, Any]] = []
    draft_plan_status: str = "in_progress"
    issues: list[str] = []


# ── Critic block ────────────────────────────────────────────────────────────


def _fast_params(timeout: float) -> LLMCallParameters:
    return LLMCallParameters(thinking_enabled=False, reasoning_effort="low", timeout=timeout, max_retries=1)


def _critic_user_prompt(block_input: _CriticInput) -> str:
    payload = {
        "request": {
            "user_goal": block_input.planner_input.user_goal,
            "sub_asks": block_input.planner_input.sub_asks,
            "constraints": block_input.planner_input.constraints,
            "open_questions": block_input.planner_input.open_questions,
        },
        "draft_plan_summary": block_input.plan_summary,
        "draft_steps": block_input.draft_steps,
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class _CriticReasoningBlock(BaseReasoningBlock):
    """One council critic. Single-shot, no tools. Fails to an EMPTY issue
    list (`schema_valid=False`) -- a critic that can't run must never block
    the council, only forgo its own findings."""

    def __init__(self, *, llm_adapter: LLMAdapter, prompt_registry: PromptRegistry, contract_name: str, **kwargs: Any) -> None:
        super().__init__(llm_adapter=llm_adapter, prompt_registry=prompt_registry, **kwargs)
        self._contract_name = contract_name

    async def _run_internal(self, block_input: _CriticInput, telemetry: RunTelemetry) -> _CriticOutput:
        contract = self._resolve_prompt_contract(self._contract_name)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=_critic_user_prompt(block_input),
            params=params,
            response_schema=block_input.output_schema,
            phase="pass1_of_1",
            block_input=block_input,
            telemetry=telemetry,
        )
        normalized = self._normalize_result(call_result.parsed, output_schema=block_input.output_schema)
        validation = self._validate_schema(normalized, block_input.output_schema)
        if not validation.valid:
            repair = await self._repair_schema(
                initial_result=normalized,
                initial_errors=validation.errors,
                output_schema=block_input.output_schema,
                max_attempts=_MAX_SCHEMA_REPAIR_ATTEMPTS,
                block_input=block_input,
                telemetry=telemetry,
            )
            if not repair.valid:
                return self._empty_output(extra_warning="schema_validation_failed")
            normalized = repair.result

        raw_issues = normalized.get("issues")
        issues = [str(item) for item in raw_issues if str(item).strip()] if isinstance(raw_issues, list) else []
        return _CriticOutput(status="completed", schema_valid=True, result=normalized, confidence=1.0, issues=issues)

    def _empty_output(self, *, extra_warning: str | None = None) -> _CriticOutput:
        warnings = ["planner_critic_no_findings"]
        if extra_warning:
            warnings.append(extra_warning)
        return _CriticOutput(status="completed", schema_valid=False, result=None, confidence=0.0, warnings=warnings, issues=[])

    def _failed_output(self, block_input: BaseReasoningBlockInput, *, reason: str) -> _CriticOutput:
        return self._empty_output(extra_warning=f"reasoning_block_failed: {reason}")


# ── Synthesizer block ───────────────────────────────────────────────────────


def _synth_user_prompt(block_input: _SynthesizerInput) -> str:
    payload = {
        "request": {
            "user_goal": block_input.planner_input.user_goal,
            "sub_asks": block_input.planner_input.sub_asks,
            "constraints": block_input.planner_input.constraints,
            "open_questions": block_input.planner_input.open_questions,
        },
        "draft_plan_status": block_input.draft_plan_status,
        "draft_steps": block_input.draft_steps,
        "critic_issues": block_input.issues,
        "output_schema_name": block_input.output_schema_name,
        "output_schema": block_input.output_schema,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


class _SynthesizerReasoningBlock(PlannerReasoningBlock):
    """Reuses PlannerReasoningBlock's whole validate/repair/hollow-check and
    fail-closed `_to_output`/`_fallback_output` machinery -- it produces the
    identical output shape -- overriding only the user prompt so it revises a
    draft against critic issues instead of planning from scratch."""

    async def _run_internal(self, block_input: _SynthesizerInput, telemetry: RunTelemetry) -> PlannerReasoningBlockOutput:
        contract = self._resolve_prompt_contract(SYNTHESIZER_V1)
        params = self._resolve_llm_call_parameters(block_input.llm_call_parameters, contract)
        call_result = await self._invoke_llm(
            system_prompt=_build_system_prompt(contract),
            user_prompt=_synth_user_prompt(block_input),
            params=params,
            response_schema=block_input.output_schema,
            phase="pass1_of_1",
            block_input=block_input,
            telemetry=telemetry,
        )
        normalized = self._normalize_result(call_result.parsed, output_schema=block_input.output_schema)
        validation = self._validate_schema(normalized, block_input.output_schema)
        if not validation.valid:
            repair = await self._repair_schema(
                initial_result=normalized,
                initial_errors=validation.errors,
                output_schema=block_input.output_schema,
                max_attempts=_MAX_SCHEMA_REPAIR_ATTEMPTS,
                block_input=block_input,
                telemetry=telemetry,
            )
            if not repair.valid:
                return self._fallback_output(block_input, extra_warning="schema_validation_failed")
            normalized = repair.result
        return self._to_output(normalized, block_input)


# ── Council orchestration ───────────────────────────────────────────────────


def _draft_steps_as_dicts(output: PlannerReasoningBlockOutput) -> list[dict[str, Any]]:
    return [step.model_dump() for step in output.next_steps]


def _should_run_full_council(invocation: int, planner_input: PlannerInvocationInput) -> bool:
    """Adaptive depth: the critic+synth pass runs only where the plan's SHAPE
    is genuinely at stake --

    - the FIRST invocation of a (sub)plan, where getting the step
      decomposition, coverage, and success_criteria right sets up everything
      downstream, and
    - any invocation the Monitor triggered as a REPLAN (non-empty
      monitor_flags or a replan_reason), where the previous attempt hit a
      problem and the new plan needs to actually fix it.

    Every OTHER invocation is a routine continuation -- the plan is already
    working and the Planner is just emitting the next mechanical batch. The
    critics add little there, and the Planner is invoked many times per turn,
    so running the full council every time is exactly the cost this gate
    removes (roughly halving planner-side calls) without touching the cases
    where the council earns its keep.
    """
    if invocation <= 1:
        return True
    return bool(planner_input.monitor_flags or planner_input.replan_reason)


async def run_planner_council(
    *,
    planner_input: PlannerInvocationInput,
    llm_adapter: LLMAdapter,
    block_id: str,
    invocation: int = 1,
    prompt_contract_name: str = PLANNER_V1,
    output_schema_name: str,
    output_schema: dict[str, Any],
    critics: tuple[str, ...] = _DEFAULT_CRITICS,
    drafter_timeout: float = _DRAFTER_TIMEOUT,
    critic_timeout: float = _CRITIC_TIMEOUT,
    synthesizer_timeout: float = _SYNTH_TIMEOUT,
) -> PlannerReasoningBlockOutput:
    """Draft -> (adaptively) parallel critics -> gated synthesis. Returns the
    same `PlannerReasoningBlockOutput` a single `PlannerReasoningBlock.run()`
    would, so it drops straight into `build_next_plan_steps`.

    `invocation` drives the adaptive-depth gate (`_should_run_full_council`):
    a routine continuation runs the fast drafter alone; the first invocation
    and Monitor-flagged replans run the full council. The council is only ever
    used by the TOP-LEVEL planner now -- nested step decomposition moved to the
    Specialist Router, which is a single fast call and never runs critics."""
    registry = build_council_prompt_registry()

    # 1. DRAFT -- the existing planner block, fast (no thinking).
    draft_block = PlannerReasoningBlock(llm_adapter=llm_adapter)
    draft_output = await draft_block.run(
        PlannerReasoningBlockInput(
            block_id=f"{block_id}-draft",
            agent_name="planner_council_drafter",
            objective=planner_input.user_goal,
            output_schema_name=output_schema_name,
            output_schema=output_schema,
            prompt_contract_name=prompt_contract_name,
            planner_input=planner_input,
            llm_call_parameters=_fast_params(drafter_timeout),
        )
    )

    # Gate: a failed draft (fail-closed already) or one with no runnable
    # steps has nothing for the council to improve -- return it as-is. This
    # also skips the critic+synth calls for trivial invocations (a genuine
    # clarification block, or a plan that legitimately produced no new steps).
    if not draft_output.schema_valid or not draft_output.next_steps:
        return draft_output

    # Adaptive depth: a routine continuation (not the first invocation, no
    # replan flags) trusts the fast draft as-is and skips the critic+synth
    # calls entirely -- see _should_run_full_council.
    if not _should_run_full_council(invocation, planner_input):
        return draft_output.model_copy(
            update={"warnings": [*draft_output.warnings, "planner_council_draft_only"]}
        )

    draft_steps = _draft_steps_as_dicts(draft_output)

    # 2. CRITICS -- in parallel; a failed/slow critic contributes nothing.
    async def _run_critic(contract_name: str) -> list[str]:
        block = _CriticReasoningBlock(
            llm_adapter=llm_adapter, prompt_registry=registry, contract_name=contract_name
        )
        out = await block.run(
            _CriticInput(
                block_id=f"{block_id}-{contract_name}",
                agent_name=contract_name,
                objective="Review the draft plan for one class of defect.",
                output_schema_name=_CRITIC_OUTPUT_SCHEMA_NAME,
                output_schema=_CRITIC_OUTPUT_SCHEMA,
                prompt_contract_name=contract_name,
                planner_input=planner_input,
                draft_steps=draft_steps,
                plan_summary=draft_output.plan_summary,
                llm_call_parameters=_fast_params(critic_timeout),
            )
        )
        return list(out.issues)

    critic_results = await asyncio.gather(*(_run_critic(name) for name in critics), return_exceptions=True)
    issues: list[str] = []
    for result in critic_results:
        if isinstance(result, BaseException):
            logger.warning("planner_council_critic_raised", exc_info=result)
            continue
        issues.extend(result)

    # Gate: no findings -> the draft already stands, skip the synth call.
    if not issues:
        return draft_output

    # 3. SYNTHESIZE -- revise the draft to fix the issues. If it fails, the
    # draft is already a valid plan, so fall back to it rather than to a
    # clarification block.
    synth_block = _SynthesizerReasoningBlock(llm_adapter=llm_adapter, prompt_registry=registry)
    synth_output = await synth_block.run(
        _SynthesizerInput(
            block_id=f"{block_id}-synth",
            agent_name="planner_council_synthesizer",
            objective=planner_input.user_goal,
            output_schema_name=output_schema_name,
            output_schema=output_schema,
            prompt_contract_name=SYNTHESIZER_V1,
            planner_input=planner_input,
            draft_steps=draft_steps,
            draft_plan_status=draft_output.plan_status,
            issues=issues,
            llm_call_parameters=_fast_params(synthesizer_timeout),
        )
    )
    if not synth_output.schema_valid or check_hollow_result(
        synth_output.plan_status, synth_output.next_steps, synth_output.clarification_question
    ):
        # Revision came back empty/hollow -- keep the vetted draft.
        return draft_output.model_copy(update={"warnings": [*draft_output.warnings, "planner_council_synth_discarded"]})
    return synth_output.model_copy(update={"warnings": [*synth_output.warnings, "planner_council_synthesized"]})


__all__ = [
    "COVERAGE_CRITIC_V1",
    "GROUNDING_CRITIC_V1",
    "CRITERIA_CRITIC_V1",
    "PARSIMONY_CRITIC_V1",
    "STRATEGY_CRITIC_V1",
    "DOMAIN_CRITIC_V1",
    "SYNTHESIZER_V1",
    "build_council_prompt_registry",
    "run_planner_council",
]
