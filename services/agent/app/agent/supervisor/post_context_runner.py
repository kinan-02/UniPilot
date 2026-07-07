"""Post-context/post-live-workflow Supervisor Shadow Compare runner (Phase 8/9).

Phase 6/7's supervisor diagnostic call (`supervisor.diagnostics.run_supervisor_dry_run`)
runs *before* a live `AgentContextPack` exists, so it can never supply a
populated `SupervisorRuntimeContext` — no Phase 7 real handler has ever run
automatically from a live turn as a result (see `docs/agent/CURRENT_STATE.md`
Phase 7 section).

`run_post_context_shadow_compare` is the safer, later hook the Phase 7 notes
deferred to Phase 8: called *after* the live workflow has already produced
its `AgentResponse`, so a real `AgentContextPack` is available. It:

1. Does nothing at all (returns `None` immediately, no DB/workflow/LLM
   calls) unless `AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED=true`.
2. Re-runs the (already normalized) `PlannerOutput`'s subtask graph through
   `run_supervisor_shadow`, with a `SupervisorRuntimeContext` that hard-forces
   `allow_side_effects=False` / `shadow_execution=True` regardless of what is
   passed in (see `schemas.SupervisorRuntimeContext`'s own validators).
3. Compares the live `AgentResponse` against the shadow run
   (`shadow_compare.build_comparison_summary`) and validates that comparison
   (`validation.validate_shadow_run`) — Phase 8 behavior, unchanged.
4. (Phase 9) When promotion is configured and eligible, also captures a full
   in-memory candidate `AgentResponse` for `graduation_progress_workflow`
   and runs it through `promotion.evaluate_promotion_decision`. Returns the
   candidate back to the caller (`orchestrator.py`) *only* in memory — never
   through any dict/diagnostics field — for the caller to use as the final
   response if (and only if) promotion was granted.
5. (Phase 11) When `AGENT_SPECIALIST_VALIDATION_ENABLED`/`AGENT_SPECIALIST_COMPARE_ENABLED`
   are configured, scans `shadow_output.subtask_records` for specialist-agent
   subtask results (Phase 10), validates each
   (`specialists.validation.validate_specialist_output`), optionally compares
   each against the live `AgentResponse`
   (`specialists.compare.compare_workflow_and_specialist`), and attaches a
   compact `specialistValidation` diagnostics dict. Never affects
   `selected_response`/`promoted_response` on its own — purely additive
   diagnostics *unless* Phase 14 text promotion (below) also passes.
6. (Phase 14) When text promotion is configured, eligible, and Phase 9
   workflow promotion did *not* already promote a candidate this turn,
   captures the full in-memory `SpecialistAgentOutput` for
   `graduation_progress_agent` (via `SpecialistAgentHandler`'s own
   `specialist_output_sink`, reusing the *same* shadow run above — never a
   second specialist pass) and runs it through
   `text_promotion.evaluate_specialist_text_promotion`. When every strict
   gate passes, builds a candidate `AgentResponse` that is a copy of the
   live response with only `text` replaced
   (`text_promotion.build_text_promoted_response`) and returns it as
   `promoted_response`, exactly like Phase 9's own candidate — the caller
   applies it the same generic way either mechanism uses.

Hard constraints (see also `runtime.py`'s own docstring, which this reuses
unchanged):
- Never mutates the `AgentResponse` passed in, never emits a `StreamEvent`,
  never persists an assistant message or action proposal, never writes to
  Mongo. This function has no side effects of its own beyond the read-only
  workflow re-execution `run_supervisor_shadow` may perform internally.
- Never raises into a live turn: every failure mode (missing inputs, a
  supervisor bug, an unexpected exception) resolves to `None`, exactly like
  `supervisor.diagnostics.run_supervisor_dry_run`.
- Never calls an LLM directly. `general_academic_workflow` (the one
  read-only workflow that may call an LLM through the existing
  `ReasoningBlock` path) is excluded from real shadow execution by default
  via `CapabilityExecutionMetadata.operationally_expensive_for_shadow_execution`
  — see `runtime._select_handler` — so this runner cannot trigger a new LLM
  call regardless of flags. It is also simply never promotion-eligible (see
  `promotion._HARD_ALLOWED_PROMOTION_WORKFLOWS`).
- Promotion (Phase 9) is additionally gated on `AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED=true`
  — a candidate can only ever be captured from a *real* execution, and this
  module never registers a real handler when that flag is off (doing so
  would bypass `runtime._select_handler`'s own real-handlers gate).
- Text promotion (Phase 14) never runs a second specialist pass: it reuses
  the exact same `run_supervisor_shadow` call already made for Phase 8/11
  diagnostics, capturing the specialist's full in-memory output via a sink
  passed into `SpecialistAgentHandler` only for `graduation_progress_agent`,
  only when text promotion could apply. It defers unconditionally to Phase 9
  workflow promotion (`workflow_promotion_already_promoted`) and never
  promotes anything beyond `AgentResponse.text` — blocks/warnings/sources/
  proposed_actions always come from the live response unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.agent.capabilities.default_registry import build_default_capability_registry
from app.agent.schemas import AgentResponse
from app.agent.supervisor.compare_diagnostics import build_supervisor_validation_metadata
from app.agent.supervisor.handler_registry import build_default_handler_registry
from app.agent.supervisor.output_summarizer import summarize_agent_response
from app.agent.supervisor.promotion import eligible_promotion_workflows, evaluate_promotion_decision
from app.agent.supervisor.promotion_diagnostics import build_supervisor_promotion_metadata
from app.agent.supervisor.runtime import run_supervisor_shadow
from app.agent.supervisor.schemas import ExecutionBudget, SupervisorRunInput, SupervisorRuntimeContext
from app.agent.supervisor.shadow_compare import build_comparison_summary
from app.agent.supervisor.validation import validate_shadow_run
from app.agent.supervisor.workflow_adapters import ReadOnlyWorkflowAdapterHandler
from app.config import Settings, get_settings

if TYPE_CHECKING:  # pragma: no cover — type-checking only, avoids the runtime circular import below
    from app.agent.specialists.schemas import SpecialistAgentOutput

logger = logging.getLogger(__name__)

# Phase 14: the only specialist capability name ever registered with a
# sink-having `SpecialistAgentHandler` here — further intersected with
# `text_promotion.eligible_text_promotion_agents(cfg)` at call time, so a
# misconfigured `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS` can only narrow
# this, never widen it.
_TEXT_PROMOTION_ELIGIBLE_WORKFLOW = "graduation_progress_workflow"


@dataclass(frozen=True)
class PostContextShadowCompareOutcome:
    """In-memory-only result of one post-context shadow compare (+ optional
    promotion evaluation) call.

    `promoted_response` is a live `AgentResponse` Python object — never
    serialized into `validation_metadata`/`promotion_metadata`/
    `specialist_text_promotion_metadata`, and never stored anywhere by this
    module. The caller (`orchestrator.py`) decides whether to use it as the
    turn's final response and is responsible for letting it go out of scope
    (discarded) once the turn finishes; nothing here persists it. It may
    come from Phase 9 workflow promotion, Phase 14 specialist text promotion,
    or Phase 22 synthesis text promotion — never more than one for the same turn
    (later phases defer when `promoted_response` is already set).
    """

    validation_metadata: dict[str, Any] | None = None
    promotion_metadata: dict[str, Any] | None = None
    promoted_response: AgentResponse | None = None
    specialist_validation_metadata: dict[str, Any] | None = None
    specialist_text_promotion_metadata: dict[str, Any] | None = None
    dynamic_agents_metadata: dict[str, Any] | None = None
    monitor_metadata: dict[str, Any] | None = None
    clarification_metadata: dict[str, Any] | None = None
    clarification_output: Any | None = None
    plan_repair_metadata: dict[str, Any] | None = None
    synthesis_metadata: dict[str, Any] | None = None
    synthesis_promotion_metadata: dict[str, Any] | None = None


def _supervisor_output_summary(shadow_output: Any) -> dict[str, Any]:
    return {
        "status": shadow_output.status,
        "capabilities": sorted({record.capability_name for record in shadow_output.subtask_records}),
        "failedSubtasks": list(shadow_output.failed_subtasks),
        "skippedSubtasks": list(shadow_output.skipped_subtasks),
    }


async def run_post_context_shadow_compare(
    *,
    database: Any,
    agent_context_pack: Any | None,
    user_message: str,
    user_id: str | None,
    conversation_id: str | None,
    run_id: str | None,
    live_workflow_name: str | None,
    live_response: AgentResponse | None,
    planner_output: dict[str, Any] | None,
    task_understanding_summary: dict[str, Any] | None = None,
    deterministic_intent: str | None = None,
    deterministic_entities: dict[str, Any] | None = None,
    conversation_entities: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    profile_summary: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> PostContextShadowCompareOutcome | None:
    """Run the Phase 8 post-context shadow compare + validation (and, when
    configured, Phase 9's promotion evaluation), or `None`.

    Returns `None` (never raises) when: the feature flag is off, there is no
    `planner_output` to run a subtask graph from, there is no `live_response`
    to compare against, or the shadow run/comparison/validation pipeline
    itself fails unexpectedly. Otherwise always returns a fully populated
    `PostContextShadowCompareOutcome` — `promotion_metadata`/
    `promoted_response` are `None` within it whenever promotion wasn't
    configured/eligible/successful for this turn (the ordinary case).

    `agent_context_pack` may be `None` — real handlers simply never run in
    that case (the same "missing runtime context" fallback Phase 7 already
    has in `runtime._select_handler`), but supervisor graph *mechanics*
    still run in dry-run mode and a (dry-run-only) comparison is still
    produced. Promotion can never happen in that case either (no real
    candidate is ever captured).
    """
    cfg = settings or get_settings()
    if not cfg.is_agent_supervisor_post_context_compare_enabled():
        return None
    if planner_output is None or live_response is None:
        return None

    try:
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
            task_understanding=task_understanding_summary,
            deterministic_intent=deterministic_intent,
            deterministic_entities=dict(deterministic_entities or {}),
            conversation_entities=dict(conversation_entities or {}),
            conversation_assumptions=list(conversation_assumptions or []),
            profile_summary=dict(profile_summary or {}),
            dry_run=cfg.is_agent_supervisor_dry_run(),
            budget=ExecutionBudget(),
        )

        real_handlers_enabled = cfg.is_agent_supervisor_real_handlers_enabled()
        promotion_may_apply = (
            cfg.is_agent_supervisor_promotion_enabled()
            and cfg.agent_supervisor_promotion_mode() == "promote_validated"
            and bool(live_workflow_name)
            and live_workflow_name in eligible_promotion_workflows(cfg)
            and real_handlers_enabled
        )

        # Phase 14: imported lazily (see `handler_registry.py`'s own lazy
        # specialists import for the same reason) -- avoids a module-load-
        # order-dependent circular import between the `supervisor` and
        # `specialists` packages. By call time (a live/test turn, never at
        # import time) both packages are always already fully loaded.
        from app.agent.specialists.text_promotion import eligible_text_promotion_agents

        # Cheap, settings-only pre-check -- avoids building a sink/custom
        # handler registry at all when a real candidate could never be
        # captured this turn. Mirrors `promotion_may_apply`'s own shape:
        # gated on `mode == "promote_validated"` since `shadow_only`/"off"
        # never need a real in-memory specialist output -- the gate itself
        # (evaluated unconditionally below, whenever the flag is merely
        # *enabled*) returns "skipped" for those modes before ever looking
        # at specialist output.
        text_promotion_sink_may_apply = (
            cfg.is_agent_specialist_text_promotion_enabled()
            and cfg.agent_specialist_text_promotion_mode() == "promote_validated"
            and live_workflow_name == _TEXT_PROMOTION_ELIGIBLE_WORKFLOW
            and bool(eligible_text_promotion_agents(cfg))
        )

        candidate_sink: dict[str, AgentResponse] = {}
        specialist_output_sink: dict[str, "SpecialistAgentOutput"] = {}
        handler_registry = None
        if promotion_may_apply or text_promotion_sink_may_apply:
            # Only ever enables *real workflow* handlers when
            # `promotion_may_apply` (`real_handlers_enabled` gate) -- text
            # promotion alone never bypasses that gate; it only overrides
            # the (already-always-registered, see `handler_registry.py`)
            # specialist-agent handler with one that also captures its full
            # output for `graduation_progress_agent`.
            handler_registry = build_default_handler_registry(
                enable_real_read_only_handlers=promotion_may_apply, settings=cfg
            )
            if promotion_may_apply:
                handler_registry.register_for_capability_name(
                    live_workflow_name, ReadOnlyWorkflowAdapterHandler(candidate_sink=candidate_sink)
                )
            if text_promotion_sink_may_apply:
                # Imported lazily for the same reason as the specialist
                # diagnostics import further below -- avoids a module-load-
                # order-dependent circular import between `supervisor` and
                # `specialists`.
                from app.agent.specialists.supervisor_handler import SpecialistAgentHandler

                specialist_handler = SpecialistAgentHandler(specialist_output_sink=specialist_output_sink, settings=cfg)
                for agent_name in eligible_text_promotion_agents(cfg):
                    handler_registry.register_for_capability_name(agent_name, specialist_handler)

        shadow_output = await run_supervisor_shadow(
            input=run_input, handler_registry=handler_registry, runtime_context=runtime_context, settings=cfg
        )

        capability_registry = build_default_capability_registry()
        comparison = build_comparison_summary(
            live_workflow_name=live_workflow_name,
            live_response=live_response,
            shadow_run_output=shadow_output,
            capability_registry=capability_registry,
        )

        diagnostics_for_validation = {
            "budget": shadow_output.diagnostics.get("budget"),
            "blackboardSummary": shadow_output.blackboard_summary,
            "subtaskResultSummaries": {
                record.subtask_id: record.result_summary for record in shadow_output.subtask_records
            },
        }
        validation_result = validate_shadow_run(
            comparison=comparison,
            shadow_run_output=shadow_output,
            diagnostics=diagnostics_for_validation,
            validation_enabled=cfg.is_agent_supervisor_validation_enabled(),
        )
        validation_metadata = build_supervisor_validation_metadata(validation_result)

        promotion_metadata: dict[str, Any] | None = None
        promoted_response: AgentResponse | None = None
        if cfg.is_agent_supervisor_promotion_enabled():
            supervisor_output_summary = _supervisor_output_summary(shadow_output)
            live_response_summary = summarize_agent_response(
                live_response, workflow_name=live_workflow_name or "", shadow_executed=False
            )
            candidate_response = candidate_sink.get(live_workflow_name or "")
            candidate_response_summary = (
                summarize_agent_response(candidate_response, workflow_name=live_workflow_name or "", shadow_executed=True)
                if candidate_response is not None
                else None
            )

            decision = evaluate_promotion_decision(
                workflow_name=live_workflow_name or "",
                live_response_summary=live_response_summary,
                candidate_response_summary=candidate_response_summary,
                supervisor_validation=validation_result,
                supervisor_output_summary=supervisor_output_summary,
                settings=cfg,
                live_response=live_response,
                candidate_response=candidate_response,
            )
            promotion_metadata = build_supervisor_promotion_metadata(decision)
            if decision.promoted and candidate_response is not None:
                promoted_response = candidate_response

        specialist_validation_metadata: dict[str, Any] | None = None
        if cfg.is_agent_specialist_validation_enabled() or cfg.is_agent_specialist_compare_enabled():
            # Imported lazily (see `handler_registry.py`'s own lazy specialists
            # import for the same reason): avoids a module-load-order-dependent
            # circular import between the `supervisor` and `specialists`
            # packages. By call time (a live/test turn, never at import time)
            # both packages are always already fully loaded.
            from app.agent.specialists.diagnostics import (
                build_specialist_compare_diagnostics,
                build_specialist_validation_metadata,
            )

            specialist_diagnostics = build_specialist_compare_diagnostics(
                shadow_run_output=shadow_output,
                live_workflow_name=live_workflow_name,
                live_response=live_response,
                validation_enabled=cfg.is_agent_specialist_validation_enabled(),
                compare_enabled=cfg.is_agent_specialist_compare_enabled(),
            )
            if specialist_diagnostics is not None:
                specialist_validation_metadata = build_specialist_validation_metadata(specialist_diagnostics)

        dynamic_agents_metadata: dict[str, Any] | None = None
        if cfg.is_agent_dynamic_agents_enabled():
            from app.agent.dynamic_agents.diagnostics import build_dynamic_agents_metadata_from_subtask_summaries

            dynamic_agents_metadata = build_dynamic_agents_metadata_from_subtask_summaries(
                [record.result_summary for record in shadow_output.subtask_records]
            )

        monitor_metadata: dict[str, Any] | None = None
        if cfg.is_agent_monitor_enabled():
            from app.agent.monitoring.diagnostics import build_monitor_metadata
            from app.agent.monitoring.monitor import build_monitor_input_from_shadow_context, monitor_plan_execution

            monitor_input = build_monitor_input_from_shadow_context(
                planner_output=planner_output,
                shadow_run_output=shadow_output,
                task_understanding=task_understanding_summary,
                conversation_assumptions=list(conversation_assumptions or []),
                latest_user_message=user_message,
                validation_metadata=validation_metadata,
                promotion_metadata=promotion_metadata,
                specialist_validation_metadata=specialist_validation_metadata,
                dynamic_agent_metadata=dynamic_agents_metadata,
            )
            monitor_output = monitor_plan_execution(
                monitor_input,
                enabled=True,
                dry_run=cfg.is_agent_monitor_dry_run(),
            )
            monitor_metadata = build_monitor_metadata(monitor_output)

        clarification_metadata: dict[str, Any] | None = None
        clarification_output = None
        if cfg.is_agent_clarification_enabled():
            from app.agent.clarification.capability import run_clarification_from_shadow_context
            from app.agent.clarification.diagnostics import build_clarification_metadata

            clarification_output = run_clarification_from_shadow_context(
                monitor_metadata=monitor_metadata,
                planner_output=planner_output if isinstance(planner_output, dict) else None,
                allow_user_questions=cfg.is_agent_clarification_user_facing_enabled(),
                max_questions=max(1, int(cfg.agent_clarification_max_questions)),
            )
            clarification_metadata = build_clarification_metadata(clarification_output)

        plan_repair_metadata: dict[str, Any] | None = None
        if cfg.is_agent_plan_repair_enabled():
            from app.agent.planner.repair_diagnostics import run_plan_repair_diagnostics

            _repair_output, plan_repair_metadata = await run_plan_repair_diagnostics(
                user_goal=user_message,
                planner_output=planner_output if isinstance(planner_output, dict) else None,
                monitor_metadata=monitor_metadata,
                workflow_name=live_workflow_name,
                intent=deterministic_intent,
                current_user_message=user_message,
                settings=cfg,
            )

        specialist_text_promotion_metadata: dict[str, Any] | None = None
        if cfg.is_agent_specialist_text_promotion_enabled():
            # Evaluated whenever the flag is merely *enabled* -- mirrors
            # `if cfg.is_agent_supervisor_promotion_enabled():` above.
            # `evaluate_specialist_text_promotion` itself returns
            # `status="skipped"` immediately for `"off"`/`"shadow_only"`
            # mode, before ever looking at specialist output, so a real
            # candidate/sink is never required for those modes.
            #
            # Imported lazily -- see the comment on the earlier
            # `eligible_text_promotion_agents` import above for why.
            from app.agent.specialists.text_promotion import (
                build_text_promoted_response,
                evaluate_specialist_text_promotion,
            )
            from app.agent.specialists.text_promotion_diagnostics import build_specialist_text_promotion_metadata

            target_agent_name = next(iter(eligible_text_promotion_agents(cfg)), None)
            specialist_output_summary = next(
                (
                    record.result_summary
                    for record in shadow_output.subtask_records
                    if record.capability_name == target_agent_name
                ),
                None,
            )
            comparisons = (specialist_validation_metadata or {}).get("comparisons") or []
            specialist_comparison_metadata = next(
                (
                    comparison
                    for comparison in comparisons
                    if isinstance(comparison, dict) and comparison.get("specialistAgentName") == target_agent_name
                ),
                None,
            )
            raw_specialist_output = specialist_output_sink.get(target_agent_name or "")
            answer_text: str | None = None
            if raw_specialist_output is not None and isinstance(raw_specialist_output.result, dict):
                candidate_text = raw_specialist_output.result.get("answer_text")
                if isinstance(candidate_text, str):
                    answer_text = candidate_text

            live_response_summary_for_text = summarize_agent_response(
                live_response, workflow_name=live_workflow_name or "", shadow_executed=False
            )

            text_decision = evaluate_specialist_text_promotion(
                workflow_name=live_workflow_name or "",
                specialist_agent_name=target_agent_name,
                live_response_summary=live_response_summary_for_text,
                specialist_validation_metadata=specialist_validation_metadata,
                specialist_comparison_metadata=specialist_comparison_metadata,
                specialist_output_summary=specialist_output_summary,
                answer_text=answer_text,
                workflow_promotion_already_promoted=promoted_response is not None,
                settings=cfg,
            )
            specialist_text_promotion_metadata = build_specialist_text_promotion_metadata(text_decision)

            if text_decision.promoted and promoted_response is None and answer_text:
                promoted_response = build_text_promoted_response(live_response=live_response, answer_text=answer_text)

        synthesis_metadata: dict[str, Any] | None = None
        synthesis_output = None
        if cfg.is_agent_synthesis_enabled():
            from app.agent.planner.dynamic_spec_diagnostics import build_planner_dynamic_agents_metadata
            from app.agent.synthesis.synthesis_agent import run_synthesis_diagnostics

            live_response_summary_for_synthesis = summarize_agent_response(
                live_response,
                workflow_name=live_workflow_name or "",
                shadow_executed=False,
            ) if live_response is not None else {}

            planner_dynamic = None
            if isinstance(planner_output, dict):
                dynamic_diag = planner_output.get("dynamic_spec_diagnostics") or planner_output.get(
                    "dynamicSpecDiagnostics"
                )
                if isinstance(dynamic_diag, dict):
                    planner_dynamic = build_planner_dynamic_agents_metadata(
                        dynamic_diag,
                        dynamic_agents_metadata=dynamic_agents_metadata,
                    )

            supervisor_bundle = {
                "supervisorValidation": validation_metadata,
                "supervisorPromotion": promotion_metadata,
                "specialistValidation": specialist_validation_metadata,
                "specialistTextPromotion": specialist_text_promotion_metadata,
                "dynamicAgents": dynamic_agents_metadata,
                "monitorDiagnostics": monitor_metadata,
                "clarificationDiagnostics": clarification_metadata,
                "planRepairDiagnostics": plan_repair_metadata,
                "plannerDiagnostics": {"plannerDynamicAgents": planner_dynamic} if planner_dynamic else {},
            }

            synthesis_output, synthesis_metadata = await run_synthesis_diagnostics(
                user_goal=user_message,
                normalized_request=user_message,
                live_response_summary=live_response_summary_for_synthesis,
                supervisor_metadata=supervisor_bundle,
                settings=cfg,
            )

        synthesis_promotion_metadata: dict[str, Any] | None = None
        if cfg.is_agent_synthesis_text_promotion_enabled() and live_response is not None:
            from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata
            from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
            from app.agent.synthesis.response_builder import build_synthesis_text_promoted_response

            retrieval_bundle = {
                "monitorDiagnostics": monitor_metadata,
                "planRepairDiagnostics": plan_repair_metadata,
                "clarificationDiagnostics": clarification_metadata,
                "clarificationState": {},
                "supervisorPromotion": promotion_metadata,
                "specialistTextPromotion": specialist_text_promotion_metadata,
            }

            promotion_decision = evaluate_synthesis_text_promotion(
                workflow_name=live_workflow_name,
                live_response=live_response,
                synthesis_output=synthesis_output,
                retrieval_metadata=retrieval_bundle,
                settings=cfg,
                existing_promotion_already_applied=promoted_response is not None,
                workflow_promotion_already_applied=bool(promotion_metadata and promotion_metadata.get("promoted")),
                specialist_text_promotion_already_applied=bool(
                    specialist_text_promotion_metadata and specialist_text_promotion_metadata.get("promoted")
                ),
            )
            synthesis_promotion_metadata = build_synthesis_promotion_metadata(promotion_decision)

            if (
                promotion_decision.promoted
                and promoted_response is None
                and synthesis_output is not None
                and synthesis_output.candidate_answer_text
            ):
                promoted_response = build_synthesis_text_promoted_response(
                    live_response=live_response,
                    candidate_text=synthesis_output.candidate_answer_text,
                )

    except Exception:  # noqa: BLE001 — diagnostic-only path, must never break a live turn
        logger.exception("supervisor_post_context_shadow_compare_failed")
        return None

    logger.info(
        "supervisor_post_context_shadow_compare_result",
        extra={
            "supervisorValidation": validation_metadata,
            "supervisorPromotion": promotion_metadata,
            "specialistValidation": specialist_validation_metadata,
            "specialistTextPromotion": specialist_text_promotion_metadata,
            "dynamicAgents": dynamic_agents_metadata,
            "monitorDiagnostics": monitor_metadata,
            "clarificationDiagnostics": clarification_metadata,
            "planRepairDiagnostics": plan_repair_metadata,
            "synthesisDiagnostics": synthesis_metadata,
            "synthesisPromotion": synthesis_promotion_metadata,
        },
    )
    return PostContextShadowCompareOutcome(
        validation_metadata=validation_metadata,
        promotion_metadata=promotion_metadata,
        promoted_response=promoted_response,
        specialist_validation_metadata=specialist_validation_metadata,
        specialist_text_promotion_metadata=specialist_text_promotion_metadata,
        dynamic_agents_metadata=dynamic_agents_metadata,
        monitor_metadata=monitor_metadata,
        clarification_metadata=clarification_metadata,
        clarification_output=clarification_output,
        plan_repair_metadata=plan_repair_metadata,
        synthesis_metadata=synthesis_metadata,
        synthesis_promotion_metadata=synthesis_promotion_metadata,
    )
