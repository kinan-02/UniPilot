"""Controlled Planner-first live execution (post-Phase-9).

Lets the Planner's own plan, executed for real through the Supervisor
runtime, stand in for `task_planner.py` + `workflow.run()` entirely for a
capability — instead of only ever being compared against the deterministic
workflow's own result (as Phase 9 promotion does). This is a materially
bigger step than promotion: once eligible, the deterministic path is never
even consulted for that turn, so this module is deliberately more
conservative than `supervisor.promotion`:

- `is_capability_planner_first_live_eligible` never bypasses the runtime
  readiness gate when it is disabled. Phase 9 promotion does (`gate_disabled`
  -> `allowed=True`) because its worst case is "a verified block-for-block
  equivalent candidate got substituted"; this module's worst case is "a
  different code path decided and executed", so the gate must be explicitly
  turned on and a human-reviewed manifest must explicitly approve each
  workflow at `ready_for_broader_promotion` — the top rung of the readiness
  ladder, not whatever `AGENT_RUNTIME_READINESS_MIN_LEVEL` happens to be set
  to for other candidate types.
- Also requires `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED` explicitly, for
  consistency with every other real-execution path in the Supervisor stack
  — `run_planner_first_live_turn` registers its own real handler directly,
  so nothing else would otherwise enforce this master switch here.
- `_HARD_ALLOWED_PLANNER_FIRST_LIVE_WORKFLOWS` is a subset of
  `supervisor.promotion._HARD_ALLOWED_PROMOTION_WORKFLOWS` — a workflow must
  already be safely promotable via live-vs-shadow comparison before it is
  even considered for direct Planner-first execution.
- `run_planner_first_live_turn` never raises and fails closed to `None`
  (letting the caller fall back to the existing, always-safe deterministic
  workflow path) on any doubt at all: a non-"completed"/"completed_with_warnings"
  run status, any failed or skipped subtask, a missing candidate response,
  an unexpectedly-shaped candidate, or more than one capability's candidate
  captured.

Post-Phase-9 addition — proposal-capable execution (`transcript_import_workflow`,
`semester_planning_workflow`): a wholly separate eligibility gate,
`is_capability_planner_first_live_proposal_eligible`, with its own master
flag (`AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED`, independent of the
read-only flag above) and its own hard-allowed workflow set. Unlike the
read-only set, this one is *not* a subset of Phase 9's promotion-eligible
workflows — write/proposal capabilities can never go through comparison-
based promotion at all (permanently excluded there by design), so there is
no "prove it via Promotion first" stepping stone available for them; this
is the first and only real-execution axis for these two capabilities,
reviewed and gated on its own terms. When eligible, `run_planner_first_live_turn`
is called with `allow_single_proposed_action=True`, which — and only which
— lets `supervisor.runtime.run_supervisor_shadow`'s dispatch reach a
capability that `safety.can_shadow_execute_capability` alone would still
always refuse (see that module for the narrow, explicit widening this
requires) and lets the registered handler instance tolerate up to one
proposed action (never more) in its result.

Phase 4 addition — live repair-and-redispatch (`attempt_live_plan_repair`):
closes the Monitor->Planner loop for a Planner-first-live turn. When
`monitor_plan_execution` signals `request_plan_repair` mid-turn, this calls
the existing `planner.repair_diagnostics.run_plan_repair_diagnostics` (the
same deterministic/LLM repair pipeline every other repair caller uses) and
then decides, independently, whether the result is safe to actually
re-execute. It deliberately does *not* gate on `PlanRepairOutput.safe_to_use`
— that field is hardcoded `False` everywhere in `planner.repair_fallback`/
`repair_agent` by design (diagnostic-only, a separate, unrelated invariant
this module leaves fully intact for every other consumer of plan repair).
Instead, `_is_repaired_plan_safe_to_redispatch` defines its own, narrower
condition specific to this context: `mode_used == "repair"` only (never
"regenerate", whose deterministic output has zero subtasks and is not
runnable), no subtask added or removed, and every remaining subtask's
`capability_name` still equals the exact workflow already vetted eligible
for this turn — repair only ever revises subtasks already present in the
prior plan, so this can never smuggle in a new, unvetted capability.
Bounded by the existing `planner.replan_cycle_budget.ReplanCycleBudget`
(same-turn-only, not persisted across turns — an accepted limitation, not
a blocker) and attempted at most once per turn (no retry loop).

Phase 5 addition — `attempt_live_synthesis_promotion`: lets Synthesis
compose the live response's text for a Planner-first-live turn. This is
*not* a new mechanism — `synthesis.synthesis_agent.run_synthesis_diagnostics`
and `synthesis.promotion_policy.evaluate_synthesis_text_promotion` already
exist and are already wired into the *deterministic* live path (via
`supervisor.post_context_runner`, gated by `AGENT_SYNTHESIS_ENABLED` +
`AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED`/`_MODE`, both off by default).
That pipeline is simply never reached for a Planner-first-live turn, since
Phase 2 skips `run_post_context_shadow_compare` entirely for those turns
(there is no separate deterministic response left to compare against).
This function calls the exact same two entry points directly — neither
cares how `live_response` was produced, so every one of
`evaluate_synthesis_text_promotion`'s existing gates (its own hard-allowed/
excluded workflow sets — which already match Planner-first-live's own
read-only/write split exactly — its own runtime-readiness-manifest check,
monitor-safety check, no-proposed-actions check, and so on) applies exactly
as-is, deterministic-only (no generative composition), matching what the
approved plan calls for.

Layer 3 addition — specialist agents as first-class candidates: a wholly
separate, independent eligibility axis from the workflow ones above,
`is_specialist_planner_first_live_eligible`, gating whether a
`specialist_agent`-type capability's real output (already computed today,
already shadow-only) may also be captured into `run_planner_first_live_turn`'s
`candidate_sink`. Own master flag
(`AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED`), own hard-allowed set
(`_HARD_ALLOWED_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS`, deliberately just
`graduation_progress_agent` -- the only specialist whose prompt contract is
reviewed to ever populate `result["answer_text"]`), own candidate-id
namespace (`planner_first_live_specialist.<agent_name>`, parallel to, never
reused with, `planner_first_live.<workflow_name>` or Phase 14's specialist-
text-promotion namespace). Only ever meaningful when
`AGENT_PLANNER_FIRST_LIVE_MULTI_CAPABILITY_ENABLED` is also on -- there is
no legacy notion of a specialist being "the" primary capability the way a
workflow is, so a specialist-only-eligible plan dispatches nothing extra
when multi-capability mode is off. The actual `SpecialistAgentOutput` ->
`AgentResponse` mapping (text-only, deliberately narrower than even Phase
14's own gate) lives in `specialists.candidate_response`, called from
`specialists.supervisor_handler.SpecialistAgentHandler`'s own optional
`candidate_sink` param -- this module only decides *whether* a specialist
name is allowed to have its handler registered with that sink at all.

Phase 6 addition — `attempt_live_clarification`: lets a Planner-first-live
turn genuinely pause on a real user-facing clarification question, not just
receive one as a post-hoc afterthought. Same story as Phases 4/5: the
machinery already exists and is already live for the deterministic path --
`clarification.turn_handler.offer_user_facing_clarification` is called
unconditionally for every turn, but it only ever has a real
`ClarificationCapabilityOutput` to act on when
`post_context_outcome.clarification_output` is populated, which is `None`
for a Planner-first-live turn (Phase 2 skips `run_post_context_shadow_compare`
entirely there). This function calls
`clarification.capability.run_clarification_from_shadow_context` directly
-- a small, pure, synchronous function, not a new mechanism -- so
`offer_user_facing_clarification` downstream needs no changes at all: it
already generically accepts whatever `ClarificationCapabilityOutput` it's
handed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from app.agent.planner.repair_schemas import PlanRepairOutput
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentResponse
from app.agent.specialists.registry import SpecialistAgentRegistry
from app.agent.specialists.safety import is_specialist_agent_safe
from app.agent.specialists.supervisor_handler import SpecialistAgentHandler
from app.agent.supervisor.handler_registry import build_default_handler_registry
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import (
    ExecutionBudget,
    SupervisorRunInput,
    SupervisorRunOutput,
    SupervisorRuntimeContext,
)
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler
from app.config import Settings

logger = logging.getLogger(__name__)

# Deliberately a subset of `supervisor.promotion._HARD_ALLOWED_PROMOTION_WORKFLOWS`
# (which also excludes general_academic_workflow -- see that module's
# docstring for why). No configuration value can ever widen this.
_HARD_ALLOWED_PLANNER_FIRST_LIVE_WORKFLOWS: frozenset[str] = frozenset(
    {
        "graduation_progress_workflow",
        "course_question_workflow",
        "requirement_explanation_workflow",
    }
)

_REQUIRED_READINESS_LEVEL = "ready_for_broader_promotion"

_MAX_RUNTIME_MS = 30000


# Deliberately *not* a subset of `supervisor.promotion._HARD_ALLOWED_PROMOTION_WORKFLOWS`
# -- see module docstring. Both workflows here are reviewed to confirm they
# only ever call `create_agent_action_proposal`, never a direct mutation;
# the actual write stays exclusively in `api`'s separate confirm/reject flow.
_HARD_ALLOWED_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS: frozenset[str] = frozenset(
    {
        "transcript_import_workflow",
        "semester_planning_workflow",
    }
)

# Layer 3 — deliberately just the one specialist whose prompt contract Phase
# 14 already reviewed for populating `result["answer_text"]`. The other two
# specialists never populate it today, so this is the only agent that could
# ever pass `specialists.candidate_response.build_specialist_candidate_response`'s
# gate regardless of allowlist width -- kept explicit and narrow anyway,
# matching the "configured set may only narrow the hard ceiling, never widen
# it" pattern used for workflows above.
_HARD_ALLOWED_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS: frozenset[str] = frozenset(
    {
        "graduation_progress_agent",
    }
)


def planner_first_live_candidate_id(workflow_name: str) -> str:
    return f"planner_first_live.{workflow_name}"


def planner_first_live_proposal_candidate_id(workflow_name: str) -> str:
    return f"planner_first_live_proposal.{workflow_name}"


def planner_first_live_specialist_candidate_id(agent_name: str) -> str:
    return f"planner_first_live_specialist.{agent_name}"


def eligible_planner_first_live_workflows(settings: Settings) -> frozenset[str]:
    """The actual, effective Planner-first-live-eligible workflow set.

    Always a subset of `_HARD_ALLOWED_PLANNER_FIRST_LIVE_WORKFLOWS` --
    `AGENT_PLANNER_FIRST_LIVE_WORKFLOWS` may only narrow it further. Unlike
    Phase 9 promotion's configured-workflows default, this setting defaults
    to empty: an operator must explicitly opt a workflow in here, on top of
    the runtime readiness gate approval checked separately below.
    """
    return _HARD_ALLOWED_PLANNER_FIRST_LIVE_WORKFLOWS & settings.agent_planner_first_live_configured_workflows()


def _passes_top_rung_readiness_gate(*, candidate_id: str, workflow_name: str, settings: Settings) -> bool:
    """Shared readiness-gate check for both eligibility functions below.

    Deliberately not `readiness.runtime_gate.evaluate_runtime_gate_for_settings`:
    that helper bypasses to `allowed=True` when the gate is disabled and
    uses the global `AGENT_RUNTIME_READINESS_MIN_LEVEL` (shared with
    lower-stakes candidate types) rather than a level hard-pinned to the top
    rung. Both of those are wrong for a decision this consequential.
    """
    if not settings.is_agent_runtime_readiness_gate_enabled():
        return False

    from app.agent.readiness.runtime_gate import evaluate_runtime_readiness_gate, load_manifest_for_settings
    from app.agent.readiness.schemas import RuntimeReadinessGateInput

    manifest = load_manifest_for_settings(settings)
    gate_input = RuntimeReadinessGateInput(
        candidate_id=candidate_id,
        requested_scope=workflow_name,
        required_level=_REQUIRED_READINESS_LEVEL,  # type: ignore[arg-type]
        require_human_review=settings.is_agent_runtime_readiness_require_human_review(),
    )
    decision = evaluate_runtime_readiness_gate(gate_input=gate_input, manifest=manifest, settings=settings)
    return bool(decision.allowed)


def is_capability_planner_first_live_eligible(workflow_name: str, *, settings: Settings) -> bool:
    """`True` only when every gate for read-only Planner-first live execution holds.

    Never raises -- any unexpected error while evaluating readiness degrades
    to `False` (falls back to the deterministic path), never to an exception
    escaping this function.
    """
    try:
        if not settings.is_agent_planner_first_live_enabled():
            return False
        if not settings.is_agent_supervisor_real_handlers_enabled():
            # Defense in depth / consistency: every other real-execution path
            # in the Supervisor stack is gated by this same master switch.
            # `run_planner_first_live_turn` registers its own real handler
            # directly, so nothing else would otherwise enforce this here.
            return False
        if workflow_name not in eligible_planner_first_live_workflows(settings):
            return False
        return _passes_top_rung_readiness_gate(
            candidate_id=planner_first_live_candidate_id(workflow_name),
            workflow_name=workflow_name,
            settings=settings,
        )
    except Exception:  # noqa: BLE001 -- eligibility check must never break a live turn
        logger.exception("planner_first_live_eligibility_check_failed", extra={"workflowName": workflow_name})
        return False


def eligible_planner_first_live_proposal_workflows(settings: Settings) -> frozenset[str]:
    """The actual, effective proposal-capable Planner-first-live-eligible set.

    Always a subset of `_HARD_ALLOWED_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS` --
    `AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS` may only narrow it further.
    Defaults to empty, same rationale as `eligible_planner_first_live_workflows`.
    """
    return (
        _HARD_ALLOWED_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS
        & settings.agent_planner_first_live_proposal_configured_workflows()
    )


def is_capability_planner_first_live_proposal_eligible(workflow_name: str, *, settings: Settings) -> bool:
    """`True` only when every gate for proposal-capable Planner-first live
    execution holds. Independent of `is_capability_planner_first_live_eligible`
    above -- enabling one never implies the other.

    Never raises -- any unexpected error while evaluating readiness degrades
    to `False` (falls back to the deterministic path), never to an exception
    escaping this function.
    """
    try:
        if not settings.is_agent_planner_first_live_proposal_enabled():
            return False
        if not settings.is_agent_supervisor_real_handlers_enabled():
            return False
        if workflow_name not in eligible_planner_first_live_proposal_workflows(settings):
            return False
        return _passes_top_rung_readiness_gate(
            candidate_id=planner_first_live_proposal_candidate_id(workflow_name),
            workflow_name=workflow_name,
            settings=settings,
        )
    except Exception:  # noqa: BLE001 -- eligibility check must never break a live turn
        logger.exception(
            "planner_first_live_proposal_eligibility_check_failed", extra={"workflowName": workflow_name}
        )
        return False


def eligible_planner_first_live_specialist_agents(settings: Settings) -> frozenset[str]:
    """The actual, effective Planner-first-live-eligible specialist-agent set.

    Always a subset of `_HARD_ALLOWED_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS` --
    `AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS` may only narrow it further.
    """
    return (
        _HARD_ALLOWED_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS
        & settings.agent_planner_first_live_configured_specialist_agents()
    )


def is_specialist_planner_first_live_eligible(agent_name: str, *, settings: Settings) -> bool:
    """`True` only when every gate for specialist-agent Planner-first-live
    dispatch holds. Independent of both workflow eligibility functions above
    -- enabling one never implies the others.

    Checks `specialists.safety.is_specialist_agent_safe` (descriptor-level)
    rather than `supervisor.safety.can_shadow_execute_capability`, since a
    specialist agent is never a `workflow`-type capability. Never raises --
    any unexpected error while evaluating readiness degrades to `False`
    (falls back to the existing shadow-only behavior), never to an exception
    escaping this function.
    """
    try:
        if not settings.is_agent_planner_first_live_specialist_agents_enabled():
            return False
        if not settings.is_agent_supervisor_real_handlers_enabled():
            return False
        if agent_name not in eligible_planner_first_live_specialist_agents(settings):
            return False

        from app.agent.capabilities.default_registry import build_default_capability_registry

        capability = build_default_capability_registry().get(agent_name)
        if capability is None or not is_specialist_agent_safe(capability):
            return False

        return _passes_top_rung_readiness_gate(
            candidate_id=planner_first_live_specialist_candidate_id(agent_name),
            workflow_name=agent_name,
            settings=settings,
        )
    except Exception:  # noqa: BLE001 -- eligibility check must never break a live turn
        logger.exception("planner_first_live_specialist_eligibility_check_failed", extra={"agentName": agent_name})
        return False


def _distinct_capability_names(planner_output: dict[str, Any]) -> frozenset[str]:
    names = {
        str(subtask.get("capability_name") or "")
        for subtask in (planner_output.get("subtasks") or [])
        if isinstance(subtask, dict)
    }
    names.discard("")
    return frozenset(names)


def any_subtask_planner_first_live_eligible(planner_output: dict[str, Any], *, settings: Settings) -> bool:
    """`True` if any subtask's `capability_name` passes read-only or
    proposal-capable Planner-first-live eligibility.

    Layer 2 (multi-capability dispatch) replacement for checking a single
    `task_plan.workflow` -- evaluated against the Planner's own subtask
    graph instead. A cheap, side-effect-free pre-check gating whether
    `run_planner_first_live_turn` is even worth calling. Never raises.
    """
    try:
        names = _distinct_capability_names(planner_output)
        return any(
            is_capability_planner_first_live_eligible(name, settings=settings)
            or is_capability_planner_first_live_proposal_eligible(name, settings=settings)
            for name in names
        )
    except Exception:  # noqa: BLE001 -- eligibility check must never break a live turn
        logger.exception("planner_first_live_any_subtask_eligibility_check_failed")
        return False


def _eligible_capability_names_for_plan(
    planner_output: dict[str, Any],
    *,
    settings: Settings,
    allow_proposal_eligible: bool,
    primary_workflow_name: str,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Returns `(read_only_eligible_names, proposal_eligible_names,
    specialist_eligible_names)` for `planner_output`'s own subtask
    capability names.

    When `settings.is_agent_planner_first_live_multi_capability_enabled()` is
    `False` (the default), all three sets are collapsed to at most
    `{primary_workflow_name}` -- byte-for-byte today's single-capability
    substitution behavior. There is no legacy notion of a specialist being
    "the" primary capability the way a workflow is, so
    `specialist_eligible_names` is always empty when multi-capability mode
    is off. `allow_proposal_eligible=False` (the caller's own explicit
    opt-in, mirroring the pre-existing `allow_single_proposed_action`
    contract) forces `proposal_eligible_names` empty regardless of what
    individual subtasks would otherwise qualify for.
    """
    names = _distinct_capability_names(planner_output)
    read_only_names = frozenset(
        name for name in names if is_capability_planner_first_live_eligible(name, settings=settings)
    )
    proposal_names = (
        frozenset(
            name for name in names if is_capability_planner_first_live_proposal_eligible(name, settings=settings)
        )
        if allow_proposal_eligible
        else frozenset()
    )
    specialist_names = frozenset(
        name for name in names if is_specialist_planner_first_live_eligible(name, settings=settings)
    )

    if not settings.is_agent_planner_first_live_multi_capability_enabled():
        read_only_names = frozenset({primary_workflow_name}) & read_only_names
        proposal_names = frozenset({primary_workflow_name}) & proposal_names
        specialist_names = frozenset()

    return read_only_names, proposal_names, specialist_names


def _combine_planner_first_live_candidates(
    candidate_sink: dict[str, AgentResponse], *, planner_output: dict[str, Any]
) -> AgentResponse:
    """Deliberately naive concatenation of 2+ real subtask responses into one.

    This is not Synthesis/Composition (an explicitly later, out-of-scope
    layer) -- it exists only so a genuinely multi-capability Planner-first-
    live turn has *some* coherent single response today. Every entry in
    `candidate_sink` is always a full, real `AgentResponse` -- either from a
    complete `workflow.run()` call (`ReadOnlyWorkflowAdapterHandler`) or a
    text-only candidate built from a real specialist-agent call (Layer 3,
    `SpecialistAgentHandler`'s `candidate_sink` ->
    `specialists.candidate_response.build_specialist_candidate_response`) --
    so there is no partial-context-fragment shape to reconcile. Do not
    invest further in making this smarter; the eventual Synthesis/
    Composition layer will very likely replace it outright.
    """
    subtasks = [s for s in (planner_output.get("subtasks") or []) if isinstance(s, dict)]
    order: list[str] = []
    titles: dict[str, str] = {}
    for subtask in subtasks:
        name = str(subtask.get("capability_name") or "")
        if name in candidate_sink and name not in order:
            order.append(name)
            titles[name] = str(subtask.get("title") or name)
    # Defensive: include any candidate_sink entry not found in subtasks
    # (should not happen, but never silently drop a real result).
    for name in candidate_sink:
        if name not in order:
            order.append(name)
            titles[name] = name

    text_sections: list[str] = []
    blocks: list[Any] = []
    warnings: list[str] = []
    suggested_prompts: list[str] = []
    assumptions: list[str] = []
    used_sources: list[str] = []
    proposed_actions: list[Any] = []
    for name in order:
        response = candidate_sink[name]
        text_sections.append(f"### {titles[name]}\n\n{response.text}")
        blocks.extend(response.blocks)
        for warning in response.warnings:
            if warning not in warnings:
                warnings.append(warning)
        for prompt in response.suggested_prompts:
            if prompt not in suggested_prompts:
                suggested_prompts.append(prompt)
        for assumption in response.assumptions:
            if assumption not in assumptions:
                assumptions.append(assumption)
        for source in response.used_sources:
            if source not in used_sources:
                used_sources.append(source)
        proposed_actions.extend(response.proposed_actions)

    first = candidate_sink[order[0]]
    return compose_response(
        conversation_id=first.conversation_id,
        message_id="",
        run_id=first.run_id,
        text="\n\n".join(text_sections),
        blocks=blocks,
        warnings=warnings,
        suggested_prompts=suggested_prompts,
        assumptions=assumptions,
        used_sources=used_sources,
        proposed_actions=proposed_actions,
    )


async def run_planner_first_live_turn(
    *,
    database: Any,
    agent_context_pack: Any,
    user_message: str,
    user_id: str | None,
    conversation_id: str | None,
    run_id: str | None,
    workflow_name: str,
    planner_output: dict[str, Any],
    settings: Settings,
    workflow_lookup: Callable[[str], Any] | None = None,
    allow_single_proposed_action: bool = False,
    specialist_registry: SpecialistAgentRegistry | None = None,
) -> tuple[AgentResponse | None, SupervisorRunOutput | None]:
    """Execute `planner_output`'s subtask graph for real via the Supervisor.

    `specialist_registry` (Layer 3, default `None`) mirrors `workflow_lookup`'s
    own test-injection role: `None` uses the real
    `specialists.registry.build_default_specialist_agent_registry()` (via
    `SpecialistAgentHandler`'s own default), so a test can inject a fake
    registry with no real `ReasoningBlock`/LLM call, exactly like
    `workflow_lookup` avoids a real Mongo/workflow dependency.

    Layer 2 (multi-capability dispatch): every subtask whose `capability_name`
    independently passes read-only or proposal-capable Planner-first-live
    eligibility dispatches for real; anything else in the same plan degrades
    gracefully to the existing dry-run stand-in (never a failure/skip on its
    own). Returns `(candidate_response, run_output)` only when the run
    completed cleanly, at least one real candidate was captured, and at most
    one proposed action exists across all captured candidates combined.
    Returns `(None, run_output)` (or `(None, None)` on an unexpected error)
    on any doubt at all -- the caller must treat `None` as "fall back to the
    existing deterministic `workflow.run()` path", never as a turn failure.
    `workflow_name` is retained purely as a backward-compatible diagnostic
    label (logging/metadata) -- actual eligibility is computed per-subtask
    from `planner_output` itself, not from this single name.

    When `settings.is_agent_planner_first_live_multi_capability_enabled()` is
    `False` (the default), eligibility collapses to at most `workflow_name`
    alone -- byte-for-byte identical to pre-Layer-2 behavior.

    `workflow_lookup` defaults to the real workflow registry (via
    `ReadOnlyWorkflowAdapterHandler`'s own default) -- tests inject a fake
    lookup so no real Mongo/audit-client dependency is required.

    `allow_single_proposed_action` (post-Phase-9, default `False`) must only
    ever be passed `True` by a caller that has already independently
    confirmed at least one subtask's capability passes
    `is_capability_planner_first_live_proposal_eligible` -- it both lets
    `run_supervisor_shadow`'s dispatch reach a proposal-creating capability at
    all (`allow_proposal_capable_execution=True`, see `supervisor.runtime`)
    and lets the registered handler tolerate up to one proposed action (never
    more, and only from a genuinely proposal-eligible capability) in its
    result. A proposed action from a capability that is only read-only-
    eligible is still always treated as an anomaly and fails that subtask,
    regardless of this flag.
    """
    try:
        read_only_names, proposal_names, specialist_names = _eligible_capability_names_for_plan(
            planner_output,
            settings=settings,
            allow_proposal_eligible=allow_single_proposed_action,
            primary_workflow_name=workflow_name,
        )
        real_execution_allowed_capability_names = read_only_names | proposal_names | specialist_names
        if not real_execution_allowed_capability_names:
            return None, None

        candidate_sink: dict[str, AgentResponse] = {}
        handler_registry = build_default_handler_registry(enable_real_read_only_handlers=True, settings=settings)
        if read_only_names:
            read_only_handler = ReadOnlyWorkflowAdapterHandler(
                workflow_lookup=workflow_lookup,
                candidate_sink=candidate_sink,
                allow_single_proposed_action=False,
            )
            for name in read_only_names:
                handler_registry.register_for_capability_name(name, read_only_handler)
        if proposal_names:
            proposal_handler = ReadOnlyWorkflowAdapterHandler(
                workflow_lookup=workflow_lookup,
                candidate_sink=candidate_sink,
                allow_single_proposed_action=True,
            )
            for name in proposal_names:
                handler_registry.register_for_capability_name(name, proposal_handler)
        if specialist_names:
            specialist_handler = SpecialistAgentHandler(
                specialist_registry=specialist_registry,
                candidate_sink=candidate_sink,
                settings=settings,
            )
            for name in specialist_names:
                handler_registry.register_for_capability_name(name, specialist_handler)

        runtime_context = SupervisorRuntimeContext(
            database=database,
            agent_context_pack=agent_context_pack,
            user_message=user_message,
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
        )
        run_input = SupervisorRunInput(
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            user_message=user_message,
            planner_output=planner_output,
            dry_run=False,
            budget=ExecutionBudget(max_runtime_ms=_MAX_RUNTIME_MS),
        )
        run_output = await run_supervisor_shadow(
            input=run_input,
            handler_registry=handler_registry,
            runtime_context=runtime_context,
            settings=settings,
            allow_proposal_capable_execution=bool(proposal_names),
            real_execution_allowed_capability_names=real_execution_allowed_capability_names,
        )

        if run_output.status not in {"completed", "completed_with_warnings"}:
            return None, run_output
        if run_output.failed_subtasks or run_output.skipped_subtasks:
            # Conservative choice (see module docstring): a genuine failure
            # or skip anywhere in the plan aborts the whole turn rather than
            # composing a response from whichever subtasks did succeed --
            # an honestly-partial answer is Synthesis/Composition-layer work,
            # not this bridge's job.
            return None, run_output
        if not candidate_sink:
            return None, run_output

        total_proposed_actions = sum(len(response.proposed_actions) for response in candidate_sink.values())
        if total_proposed_actions > 1:
            return None, run_output

        run_output.diagnostics["realCapabilityNames"] = sorted(candidate_sink)

        if len(candidate_sink) == 1:
            return next(iter(candidate_sink.values())), run_output

        combined = _combine_planner_first_live_candidates(candidate_sink, planner_output=planner_output)
        return combined, run_output
    except Exception:  # noqa: BLE001 -- must never raise into a live turn
        logger.exception("planner_first_live_run_failed", extra={"workflowName": workflow_name})
        return None, None


def _is_repaired_plan_safe_to_redispatch(
    output: PlanRepairOutput, *, eligible_capability_names: frozenset[str]
) -> bool:
    """Phase 4's own, narrow condition for re-executing a repaired plan --
    see the module docstring for why this is independent of the permanently
    `False` `PlanRepairOutput.safe_to_use`.

    Layer 2 (multi-capability dispatch): every remaining subtask's
    `capability_name` must be a member of `eligible_capability_names` (the
    set already vetted eligible for this turn, per `planner_output` before
    repair) -- not necessarily all the same single name. Repair only ever
    revises subtasks already present in the prior plan, so this can never
    smuggle in a new, unvetted capability.
    """
    if output.mode_used != "repair":
        return False
    repaired_plan = output.repaired_plan
    if not isinstance(repaired_plan, dict):
        return False
    subtasks = repaired_plan.get("subtasks")
    if not isinstance(subtasks, list) or not subtasks:
        return False
    if output.added_subtask_ids or output.removed_subtask_ids:
        return False
    for subtask in subtasks:
        if not isinstance(subtask, dict):
            return False
        if str(subtask.get("capability_name") or "") not in eligible_capability_names:
            return False
    return True


def _repaired_planner_output_for_redispatch(
    repaired_plan: dict[str, Any], *, original_planner_output: dict[str, Any]
) -> dict[str, Any]:
    """`repair_fallback.deterministic_plan_repair`'s `repaired_plan` dict is
    a compact diagnostic shape, not a full `PlannerOutput` -- it omits
    fields like `status`/`recommended_autonomy_level`/`primary_intent` that
    a same-turn `repair`-mode revision never changes, and sets
    `execution_mode` to a diagnostic-only sentinel (`"diagnostic_repair"`)
    that isn't a valid `PlannerOutput.execution_mode` value at all. Merge
    the original plan's values back in for all of these so the result is a
    valid `PlannerOutput` shape `run_planner_first_live_turn` can dispatch.
    """
    merged = dict(original_planner_output)
    merged.update(repaired_plan)
    merged["status"] = "completed"
    merged["execution_mode"] = original_planner_output.get("execution_mode", "single_capability")
    return merged


async def attempt_live_plan_repair(
    *,
    database: Any,
    agent_context_pack: Any,
    user_message: str,
    user_id: str | None,
    conversation_id: str | None,
    run_id: str | None,
    workflow_name: str,
    planner_output: dict[str, Any],
    monitor_metadata: dict[str, Any] | None,
    settings: Settings,
    allow_single_proposed_action: bool = False,
    workflow_lookup: Callable[[str], Any] | None = None,
) -> tuple[AgentResponse | None, dict[str, Any] | None]:
    """When Monitor signals `request_plan_repair` for this turn's Planner-
    first-live run, attempt exactly one deterministic/LLM repair (via the
    same `run_plan_repair_diagnostics` every other repair caller uses) and,
    if -- and only if -- `_is_repaired_plan_safe_to_redispatch`, re-execute
    it through `run_planner_first_live_turn` again.

    Returns `(new_candidate, plan_repair_metadata)`. `new_candidate` is
    `None` whenever repair wasn't enabled, wasn't triggered, wasn't judged
    safe, or re-dispatch itself didn't produce a usable candidate -- the
    caller must keep its existing candidate in every such case, never treat
    `None` here as a turn failure. `plan_repair_metadata` is returned
    whenever a repair attempt actually ran (regardless of outcome), for
    `retrievalMetadata.planRepairDiagnostics`. Never raises.
    """
    try:
        if not settings.is_agent_planner_first_live_repair_enabled():
            return None, None

        decision = (monitor_metadata or {}).get("decision") or {}
        if str(decision.get("action") or "") != "request_plan_repair":
            return None, None

        from app.agent.planner.repair_diagnostics import run_plan_repair_diagnostics

        output, metadata = await run_plan_repair_diagnostics(
            user_goal=str((planner_output or {}).get("user_goal") or user_message),
            planner_output=planner_output,
            monitor_metadata=monitor_metadata,
            workflow_name=workflow_name,
            current_user_message=user_message,
            settings=settings,
        )
        if output is None:
            return None, metadata

        read_only_names, proposal_names, specialist_names = _eligible_capability_names_for_plan(
            planner_output,
            settings=settings,
            allow_proposal_eligible=allow_single_proposed_action,
            primary_workflow_name=workflow_name,
        )
        eligible_capability_names = read_only_names | proposal_names | specialist_names
        if not _is_repaired_plan_safe_to_redispatch(
            output, eligible_capability_names=eligible_capability_names
        ):
            return None, metadata

        redispatch_planner_output = _repaired_planner_output_for_redispatch(
            output.repaired_plan or {}, original_planner_output=planner_output
        )
        new_candidate, _run_output = await run_planner_first_live_turn(
            database=database,
            agent_context_pack=agent_context_pack,
            user_message=user_message,
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            workflow_name=workflow_name,
            planner_output=redispatch_planner_output,
            settings=settings,
            workflow_lookup=workflow_lookup,
            allow_single_proposed_action=allow_single_proposed_action,
        )
        return new_candidate, metadata
    except Exception:  # noqa: BLE001 -- must never raise into a live turn
        logger.exception("planner_first_live_repair_attempt_failed", extra={"workflowName": workflow_name})
        return None, None


async def attempt_live_synthesis_promotion(
    *,
    workflow_name: str,
    user_message: str,
    live_response: AgentResponse,
    monitor_metadata: dict[str, Any] | None,
    plan_repair_metadata: dict[str, Any] | None,
    settings: Settings,
) -> tuple[AgentResponse | None, dict[str, Any] | None, dict[str, Any] | None]:
    """Run Synthesis + Synthesis text-promotion for a Planner-first-live
    turn's `live_response` -- see the module docstring for why this reuses
    the exact same, already-tested entry points the deterministic path uses.

    Returns `(promoted_response, synthesis_metadata, synthesis_promotion_metadata)`.
    `promoted_response` is `None` unless `AGENT_SYNTHESIS_ENABLED` and
    `AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED` are both on, `workflow_name` is
    in `promotion_policy`'s own hard-allowed set (already exactly the
    read-only Planner-first-live set), and every one of
    `evaluate_synthesis_text_promotion`'s own strict gates passes --
    `live_response.proposed_actions` alone already blocks promotion there,
    so this is automatically inert for the proposal-capable path. Never
    raises; any failure degrades to `(None, None, None)`.
    """
    try:
        from app.agent.supervisor.output_summarizer import summarize_agent_response
        from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata
        from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
        from app.agent.synthesis.response_builder import build_synthesis_text_promoted_response
        from app.agent.synthesis.synthesis_agent import run_synthesis_diagnostics

        live_response_summary = summarize_agent_response(
            live_response, workflow_name=workflow_name, shadow_executed=False
        )
        supervisor_bundle = {
            "monitorDiagnostics": monitor_metadata,
            "planRepairDiagnostics": plan_repair_metadata,
        }
        synthesis_output, synthesis_metadata = await run_synthesis_diagnostics(
            user_goal=user_message,
            normalized_request=user_message,
            live_response_summary=live_response_summary,
            supervisor_metadata=supervisor_bundle,
            settings=settings,
        )

        if not settings.is_agent_synthesis_text_promotion_enabled():
            return None, synthesis_metadata, None

        retrieval_bundle = {
            "monitorDiagnostics": monitor_metadata,
            "planRepairDiagnostics": plan_repair_metadata,
            "clarificationDiagnostics": {},
            "clarificationState": {},
        }
        decision = evaluate_synthesis_text_promotion(
            workflow_name=workflow_name,
            live_response=live_response,
            synthesis_output=synthesis_output,
            retrieval_metadata=retrieval_bundle,
            settings=settings,
        )
        synthesis_promotion_metadata = build_synthesis_promotion_metadata(decision)

        if decision.promoted and synthesis_output is not None and synthesis_output.candidate_answer_text:
            promoted = build_synthesis_text_promoted_response(
                live_response=live_response, candidate_text=synthesis_output.candidate_answer_text
            )
            return promoted, synthesis_metadata, synthesis_promotion_metadata

        return None, synthesis_metadata, synthesis_promotion_metadata
    except Exception:  # noqa: BLE001 -- must never raise into a live turn
        logger.exception("planner_first_live_synthesis_attempt_failed", extra={"workflowName": workflow_name})
        return None, None, None


def attempt_live_clarification(
    *,
    planner_output: dict[str, Any],
    monitor_metadata: dict[str, Any] | None,
    settings: Settings,
) -> tuple[Any | None, dict[str, Any] | None]:
    """Build a `ClarificationCapabilityOutput` for a Planner-first-live
    turn, reusing the exact same `run_clarification_from_shadow_context`
    entry point the deterministic path already uses -- see the module
    docstring for why this is not a new mechanism.

    Returns `(clarification_output, clarification_metadata)`, both `None`
    when clarification is disabled or nothing failed to build. The caller
    (`orchestrator.run_agent_turn`) passes `clarification_output` straight
    into the existing, unchanged `offer_user_facing_clarification` call.
    Synchronous and never raises -- `run_clarification_from_shadow_context`
    itself does no I/O and calls no LLM.
    """
    try:
        if not settings.is_agent_clarification_enabled():
            return None, None

        from app.agent.clarification.capability import run_clarification_from_shadow_context
        from app.agent.clarification.diagnostics import build_clarification_metadata

        clarification_output = run_clarification_from_shadow_context(
            monitor_metadata=monitor_metadata,
            planner_output=planner_output,
            allow_user_questions=settings.is_agent_clarification_user_facing_enabled(),
            max_questions=max(1, int(settings.agent_clarification_max_questions)),
        )
        clarification_metadata = build_clarification_metadata(clarification_output)
        return clarification_output, clarification_metadata
    except Exception:  # noqa: BLE001 -- must never raise into a live turn
        logger.exception("planner_first_live_clarification_attempt_failed")
        return None, None
