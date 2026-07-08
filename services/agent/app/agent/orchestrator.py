"""Central agent controller (spec §7)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.capabilities.diagnostics import build_capability_diagnostics
from app.agent.context_builder import build_agent_context_pack
from app.agent.conversation_memory import load_conversation_memory
from app.agent.entity_resolver import resolve_entities
from app.agent.intent_router import classify_intent
from app.agent.llm_entity_extractor import resolve_entities_with_llm_fallback
from app.agent.llm_intent_classifier import classify_intent_with_llm_fallback
from app.agent.llm_response_composer import enhance_response_with_llm
from app.agent.planner.diagnostics import build_plan_with_diagnostics
from app.agent.planner.legacy_mapping import build_legacy_workflow_plan_summary
from app.agent.planner_first_live import (
    any_subtask_planner_first_live_eligible,
    attempt_live_clarification,
    attempt_live_plan_repair,
    attempt_live_synthesis_promotion,
    is_capability_planner_first_live_proposal_eligible,
    run_planner_first_live_turn,
)
from app.agent.response_composer import compose_response
from app.agent.schemas import AgentContextPack, AgentResponse, StreamEvent, StructuredBlock
from app.agent.supervisor.diagnostics import run_supervisor_dry_run
from app.agent.supervisor.post_context_runner import run_post_context_shadow_compare
from app.agent.task_planner import build_task_plan
from app.agent.task_understanding.integration import (
    build_task_understanding_diagnostic_summary,
    run_task_understanding,
    to_intent_classification,
)
from app.agent.workflows.registry import get_workflow
from app.config import Settings, get_settings
from app.repositories.agent_conversation_repository import (
    append_conversation_assumptions,
    append_conversation_entities,
    find_conversation_by_id_and_user,
)
from app.repositories.agent_message_repository import create_agent_message
from app.repositories.agent_run_repository import (
    complete_agent_run,
    create_agent_run,
    create_agent_step,
    fail_agent_run,
    update_agent_step,
)
from app.repositories.agent_tool_call_repository import (
    complete_agent_tool_call,
    create_agent_tool_call,
)

logger = logging.getLogger(__name__)


async def _persist_and_merge_conversation_assumptions(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    memory: dict[str, Any],
    clarification_resume_assumptions: list[str],
    settings: Settings,
) -> list[str]:
    conversation_assumptions = list(memory.get("assumptions") or [])
    if clarification_resume_assumptions:
        await append_conversation_assumptions(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
            assumptions=clarification_resume_assumptions,
            settings=settings,
        )
        conversation_assumptions = [*conversation_assumptions, *clarification_resume_assumptions]
    elif memory.get("assumptions"):
        await append_conversation_assumptions(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
            assumptions=list(memory["assumptions"]),
            settings=settings,
        )
    return conversation_assumptions


async def run_agent_turn(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    user_message: str,
    trigger_message_id: str,
    message_attachments: list[dict[str, Any]] | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[StreamEvent]:
    """Execute one agent turn and yield streaming events."""
    cfg = settings or get_settings()
    conversation = await find_conversation_by_id_and_user(database, conversation_id, user_id)
    if conversation is None:
        yield StreamEvent(type="run.failed", error="Conversation not found")
        return

    run = await create_agent_run(
        database,
        user_id=user_id,
        conversation_id=conversation_id,
        trigger_message_id=trigger_message_id,
        intent="unknown_or_unsupported",
        settings=cfg,
    )
    run_id = str(run["id"])
    tool_call_count = 0
    workflow_step_count = 0
    clarification_state_metadata: dict[str, Any] | None = None
    effective_user_message = user_message
    clarification_resume_assumptions: list[str] = []
    skip_clarification_offer = False
    effective_clarification_context: dict[str, Any] | None = None
    confirmed_clarification_answers: list[dict[str, Any]] = []
    clarification_assumptions_created: list[dict[str, Any]] = []
    original_user_message_for_resume: str | None = None

    try:
        if cfg.is_agent_clarification_enabled() and cfg.is_agent_clarification_state_enabled():
            from app.agent.clarification.turn_handler import process_turn_start_clarification

            start_result = await process_turn_start_clarification(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=user_message,
                run_id=run_id,
                settings=cfg,
            )
            clarification_state_metadata = start_result.state_metadata
            effective_user_message = start_result.effective_user_message
            clarification_resume_assumptions = list(start_result.resume_assumptions)
            skip_clarification_offer = start_result.skip_user_facing_offer
            confirmed_clarification_answers = list(start_result.confirmed_clarification_answers)
            clarification_assumptions_created = list(start_result.clarification_assumptions_created)
            original_user_message_for_resume = start_result.original_user_message_for_resume
            if (
                cfg.is_agent_clarification_effective_context_enabled()
                and confirmed_clarification_answers
                and original_user_message_for_resume
            ):
                from app.agent.clarification.resume import build_effective_clarification_context

                effective_clarification_context = build_effective_clarification_context(
                    original_user_message=original_user_message_for_resume,
                    confirmed_answers=confirmed_clarification_answers,
                    assumptions_created=clarification_assumptions_created,
                )

            if start_result.early_response is not None:
                final_response = await _finalize_response(
                    start_result.early_response,
                    context=AgentContextPack(
                        conversation_id=conversation_id,
                        run_id=run_id,
                        user_id=user_id,
                        intent="unknown_or_unsupported",
                    ),
                    user_message=user_message,
                    cfg=cfg,
                )
                message_id = await _persist_assistant_message(
                    database,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    response=final_response,
                    run_id=run_id,
                    settings=cfg,
                )
                final_response = final_response.model_copy(update={"message_id": message_id})
                async for event in _emit_final_response_events(final_response, run_id=run_id):
                    yield event
                await complete_agent_run(
                    database,
                    run_id=run_id,
                    user_id=user_id,
                    status="completed",
                    intent="unknown_or_unsupported",
                    retrieval_metadata=_retrieval_metadata_with_diagnostics(
                        AgentContextPack(
                            conversation_id=conversation_id,
                            run_id=run_id,
                            user_id=user_id,
                            intent="unknown_or_unsupported",
                        ),
                        None,
                        clarification_state_metadata=clarification_state_metadata,
                    ),
                    settings=cfg,
                )
                yield StreamEvent(type="run.completed", run_id=run_id, message_id=message_id)
                return

        # Layer 1 (request understanding) rollout gate. `dry_run=True` (current
        # default) preserves the exact pre-redesign sequence: the narrower
        # LLM-fallback intent classifier + entity extractor drive routing,
        # and Task Understanding is computed but discarded. `dry_run=False`
        # makes Task Understanding the single, authoritative pass instead —
        # see docs/plans and `task_understanding/integration.py`.
        if cfg.is_agent_task_understanding_dry_run():
            classification = await classify_intent_with_llm_fallback(effective_user_message, settings=cfg)
            await complete_agent_run(
                database,
                run_id=run_id,
                user_id=user_id,
                status="running",
                intent=classification.intent,
                settings=cfg,
            )

            entities = resolve_entities(
                effective_user_message,
                conversation_entities=conversation.get("entities") or {},
            )
            entities = await resolve_entities_with_llm_fallback(
                effective_user_message,
                resolved_entities=entities,
                settings=cfg,
            )
            if entities:
                await append_conversation_entities(
                    database,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    entities=entities,
                    settings=cfg,
                )

            memory = await load_conversation_memory(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                stored_assumptions=conversation.get("assumptions") or [],
                entities=entities,
            )
            conversation_assumptions = await _persist_and_merge_conversation_assumptions(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                memory=memory,
                clarification_resume_assumptions=clarification_resume_assumptions,
                settings=cfg,
            )

            task_understanding = await run_task_understanding(
                user_message=effective_user_message,
                deterministic_intent=classification.intent,
                deterministic_intent_confidence=classification.confidence,
                deterministic_entities=entities,
                existing_assumptions=conversation_assumptions,
                attachment_metadata=message_attachments,
                settings=cfg,
            )
            task_understanding_summary = build_task_understanding_diagnostic_summary(task_understanding)

            capability_diagnostics: dict[str, Any] | None = None
            if cfg.is_agent_task_understanding_enabled():
                capability_diagnostics = build_capability_diagnostics(
                    task_understanding_summary=task_understanding_summary,
                    user_message=effective_user_message,
                    deterministic_intent=classification.intent,
                    deterministic_entities=entities,
                )
        else:
            deterministic_classification = classify_intent(effective_user_message)
            await complete_agent_run(
                database,
                run_id=run_id,
                user_id=user_id,
                status="running",
                intent=deterministic_classification.intent,
                settings=cfg,
            )

            deterministic_entities = resolve_entities(
                effective_user_message,
                conversation_entities=conversation.get("entities") or {},
            )

            memory = await load_conversation_memory(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                stored_assumptions=conversation.get("assumptions") or [],
                entities=deterministic_entities,
            )
            conversation_assumptions = await _persist_and_merge_conversation_assumptions(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                memory=memory,
                clarification_resume_assumptions=clarification_resume_assumptions,
                settings=cfg,
            )

            task_understanding = await run_task_understanding(
                user_message=effective_user_message,
                deterministic_intent=deterministic_classification.intent,
                deterministic_intent_confidence=deterministic_classification.confidence,
                deterministic_entities=deterministic_entities,
                existing_entities=conversation.get("entities") or {},
                existing_assumptions=conversation_assumptions,
                recent_messages=memory.get("recentTurns") or [],
                attachment_metadata=message_attachments,
                settings=cfg,
            )
            task_understanding_summary = build_task_understanding_diagnostic_summary(task_understanding)

            # Regex-found core entities always win — preserves the guarantee
            # `resolve_entities_with_llm_fallback` gave today (never
            # overwritten by an LLM guess); task understanding may still
            # contribute anything beyond those.
            entities = {
                **task_understanding.extracted_entities,
                **{k: v for k, v in deterministic_entities.items() if v},
            }
            if entities:
                await append_conversation_entities(
                    database,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    entities=entities,
                    settings=cfg,
                )

            classification = to_intent_classification(
                task_understanding, requires_file=deterministic_classification.requires_file
            )

            capability_diagnostics: dict[str, Any] | None = None
            if cfg.is_agent_task_understanding_enabled():
                capability_diagnostics = build_capability_diagnostics(
                    task_understanding_summary=task_understanding_summary,
                    user_message=effective_user_message,
                    deterministic_intent=deterministic_classification.intent,
                    deterministic_entities=deterministic_entities,
                )

        task_plan = build_task_plan(classification)

        # Phase 5 — Planner Agent, diagnostic dry-run only. Independently
        # gated by AGENT_PLANNER_ENABLED (default off, separate from the
        # Phase 3/4 flag) — works whether or not task understanding actually
        # ran, since `build_execution_plan` falls back to
        # `deterministic_intent` + this deterministic `legacy_workflow_plan`
        # summary on its own. Never used below to pick a workflow or shape
        # the response — only logged and attached to `retrievalMetadata`.
        # `planner_output` (the full plan) is only needed by the Phase 6
        # supervisor shadow run below; `planner_diagnostics` (the compact
        # summary) is the same value Phase 5 already attached.
        planner_output, planner_diagnostics = await build_plan_with_diagnostics(
            user_message=effective_user_message,
            task_understanding_summary=task_understanding_summary,
            deterministic_intent=classification.intent,
            deterministic_entities=entities,
            conversation_entities=conversation.get("entities") or {},
            conversation_assumptions=conversation_assumptions,
            legacy_workflow_plan=build_legacy_workflow_plan_summary(
                workflow_name=task_plan.workflow,
                read_only=task_plan.read_only,
                requires_confirmation=task_plan.requires_confirmation,
                primary_intent=classification.intent,
            ),
            settings=cfg,
        )
        if effective_clarification_context is not None and planner_diagnostics is not None:
            planner_diagnostics = {
                **planner_diagnostics,
                "effectiveClarificationContext": effective_clarification_context,
            }
        if effective_clarification_context is not None and task_understanding_summary is not None:
            task_understanding_summary = {
                **task_understanding_summary,
                "effectiveClarificationContext": effective_clarification_context,
            }

        # Phase 6 — Supervisor Orchestrator Runtime, shadow/dry-run only.
        # Independently gated by AGENT_SUPERVISOR_ENABLED (default off) and
        # only runs once planner diagnostics actually produced a plan —
        # there is no subtask graph to run otherwise. Every built-in Phase 6
        # handler is a safe dry-run stand-in: no real workflow, internal
        # API, or Mongo write happens here. Never used below to pick a
        # workflow or shape the response — only logged and attached to
        # `retrievalMetadata`.
        supervisor_diagnostics = await run_supervisor_dry_run(
            user_message=effective_user_message,
            planner_diagnostics=planner_diagnostics,
            planner_output=planner_output.model_dump() if planner_output is not None else None,
            task_understanding_summary=task_understanding_summary,
            deterministic_intent=classification.intent,
            deterministic_entities=entities,
            conversation_entities=conversation.get("entities") or {},
            conversation_assumptions=conversation_assumptions,
            settings=cfg,
        )

        for label in ("Understanding your request", "Planning next steps"):
            if workflow_step_count >= cfg.agent_max_workflow_steps:
                break
            workflow_step_count += 1
            step = await create_agent_step(database, run_id=run_id, label=label, settings=cfg)
            yield StreamEvent(type="agent.step.started", label=label, run_id=run_id)
            await update_agent_step(
                database,
                step_id=str(step["id"]),
                status="completed",
                summary=f"intent={classification.intent}; workflow={task_plan.workflow}",
                settings=cfg,
            )
            yield StreamEvent(type="agent.step.completed", label=label, run_id=run_id)

        retrieval_label = "Gathering academic context"
        if workflow_step_count < cfg.agent_max_workflow_steps:
            workflow_step_count += 1
            retrieval_step = await create_agent_step(
                database,
                run_id=run_id,
                label=retrieval_label,
                settings=cfg,
            )
            yield StreamEvent(type="agent.step.started", label=retrieval_label, run_id=run_id)

            tool_call = await _record_tool_call(
                database,
                run_id=run_id,
                user_id=user_id,
                conversation_id=conversation_id,
                tool_name="context_builder",
                input_summary=f"intent={classification.intent}",
                settings=cfg,
            )
            tool_call_count += 1
            if tool_call is not None:
                yield StreamEvent(type="tool.started", label="context_builder", run_id=run_id)

            context = await build_agent_context_pack(
                database,
                conversation_id=conversation_id,
                run_id=run_id,
                user_id=user_id,
                intent=classification.intent,
                entities=entities,
                classification=classification,
                task_plan=task_plan,
                user_message=effective_user_message,
                message_attachments=message_attachments,
                assumptions=conversation_assumptions,
                settings=cfg,
            )

            if tool_call is not None:
                await complete_agent_tool_call(
                    database,
                    tool_call_id=tool_call["id"],
                    output_summary=(
                        f"validation={context.validation.status}; "
                        f"wikiSnippets={len(context.retrieved_wiki_context)}"
                    ),
                    settings=cfg,
                )
                yield StreamEvent(type="tool.completed", label="context_builder", run_id=run_id)

            await update_agent_step(
                database,
                step_id=str(retrieval_step["id"]),
                status="completed",
                summary=(
                    f"validation={context.validation.status}; "
                    f"profile={context.retrieval_profile or 'none'}; "
                    f"wikiSnippets={len(context.retrieved_wiki_context)}; "
                    f"provenance={len(context.provenance)}"
                ),
                settings=cfg,
            )
            yield StreamEvent(type="agent.step.completed", label=retrieval_label, run_id=run_id)
        else:
            context = AgentContextPack(
                conversation_id=conversation_id,
                run_id=run_id,
                user_id=user_id,
                intent=classification.intent,
                entities=entities,
                assumptions=conversation_assumptions,
            )

        if tool_call_count >= cfg.agent_max_tool_calls_per_run:
            yield StreamEvent(
                type="agent.step.failed",
                label="Tool budget exceeded",
                run_id=run_id,
                error="Maximum tool calls reached for this run.",
            )

        if context.validation.errors and context.validation.status == "partial":
            clarification = _clarification_response(context)
            if clarification is not None:
                final_response = await _finalize_response(
                    clarification,
                    context=context,
                    user_message=user_message,
                    cfg=cfg,
                )
                message_id = await _persist_assistant_message(
                    database,
                    conversation_id=conversation_id,
                    user_id=user_id,
                    response=final_response,
                    run_id=run_id,
                    settings=cfg,
                )
                final_response = final_response.model_copy(update={"message_id": message_id})
                async for event in _emit_final_response_events(final_response, run_id=run_id):
                    yield event
                await complete_agent_run(
                    database,
                    run_id=run_id,
                    user_id=user_id,
                    status="completed",
                    intent=classification.intent,
                    retrieval_profile=context.retrieval_profile,
                    retrieval_metadata=_retrieval_metadata_with_diagnostics(
                        context,
                        task_understanding_summary,
                        capability_diagnostics,
                        planner_diagnostics,
                        supervisor_diagnostics,
                    ),
                    settings=cfg,
                )
                yield StreamEvent(type="run.completed", run_id=run_id, message_id=message_id)
                return

        workflow = get_workflow(task_plan.workflow)
        final_response: AgentResponse | None = None

        # Post-Phase-9 — Controlled Planner-first live execution. Independently
        # gated by AGENT_PLANNER_FIRST_LIVE_ENABLED (default off) plus a
        # per-workflow allowlist (default empty) plus an explicitly-required
        # runtime readiness gate approval at the top rung
        # (`ready_for_broader_promotion`). When eligible, the Planner's own
        # plan is executed for real through the Supervisor and its result
        # stands in for `workflow.run()` entirely for this turn; on any doubt
        # at all (failed/skipped subtask, missing/unsafe candidate)
        # `run_planner_first_live_turn` returns `None` and this turn falls
        # through to the exact same deterministic `workflow.run()` path as
        # before this existed.
        #
        # Phase 3 (post-Phase-9) — the same mechanism additionally covers
        # the two proposal-creating workflows, gated by its own, independent
        # flag/allowlist/readiness-manifest-candidate
        # (`is_capability_planner_first_live_proposal_eligible`) -- enabling
        # the read-only case above never implies this one. When eligible,
        # `allow_single_proposed_action=True` lets the real candidate's own
        # `proposed_actions` pass through unchanged (never more than one,
        # never a direct write) instead of being treated as a failure.
        #
        # Layer 2 (Planner: genuine multi-subtask live dispatch) --
        # eligibility is evaluated against every subtask in the Planner's own
        # plan (`any_subtask_planner_first_live_eligible`), not just
        # `task_plan.workflow` alone -- `run_planner_first_live_turn` computes
        # the actual per-subtask eligible set internally and dispatches every
        # already-approved capability in the plan for real (still just one,
        # byte-for-byte as before, unless AGENT_PLANNER_FIRST_LIVE_MULTI_
        # CAPABILITY_ENABLED is also on).
        planner_first_live_used = False
        planner_first_live_run_output = None
        allow_single_proposed_action = False
        if planner_output is not None:
            planner_output_dict = planner_output.model_dump()
            planner_first_live_eligible = any_subtask_planner_first_live_eligible(
                planner_output_dict, settings=cfg
            )

            if planner_first_live_eligible:
                subtask_capability_names = {
                    str(subtask.get("capability_name") or "")
                    for subtask in (planner_output_dict.get("subtasks") or [])
                    if isinstance(subtask, dict)
                }
                subtask_capability_names.discard("")
                allow_single_proposed_action = any(
                    is_capability_planner_first_live_proposal_eligible(name, settings=cfg)
                    for name in subtask_capability_names
                )
                live_candidate, planner_first_live_run_output = await run_planner_first_live_turn(
                    database=database,
                    agent_context_pack=context,
                    user_message=effective_user_message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    workflow_name=task_plan.workflow,
                    planner_output=planner_output_dict,
                    settings=cfg,
                    allow_single_proposed_action=allow_single_proposed_action,
                )
                if live_candidate is not None:
                    final_response = live_candidate
                    planner_first_live_used = True

        if not planner_first_live_used:
            async for item in workflow.run(database, context=context, user_message=effective_user_message):
                if isinstance(item, AgentResponse):
                    final_response = item
                    continue
                if item.type in {"agent.step.started", "agent.step.completed", "agent.step.failed"}:
                    workflow_step_count += 1
                    if workflow_step_count > cfg.agent_max_workflow_steps:
                        yield StreamEvent(
                            type="agent.step.failed",
                            label=item.label,
                            run_id=run_id,
                            error="Maximum workflow steps reached.",
                        )
                        break
                yield item

        if final_response is None:
            final_response = compose_response(
                conversation_id=conversation_id,
                message_id="",
                run_id=run_id,
                text="I could not produce a response for this request.",
                warnings=["Workflow returned no response."],
            )

        # Phase 8 — Supervisor Shadow Compare + Validation, post-context/
        # post-live-workflow hook. Independently gated by
        # AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED (default off); when
        # off this call does zero DB/workflow/LLM work (see
        # `post_context_runner.run_post_context_shadow_compare`). Compares
        # the *pre-LLM-enhancement* `final_response` (the deterministic
        # workflow's own output — blocks/warnings/proposed_actions are never
        # touched by `_finalize_response` below) against a fresh supervisor
        # shadow run of the same plan over the same live `context`.
        #
        # Phase 9 — Controlled Supervisor Promotion. Independently gated by
        # AGENT_SUPERVISOR_PROMOTION_ENABLED + AGENT_SUPERVISOR_PROMOTION_MODE
        # (both default off/"off"); when disabled this changes nothing here
        # (`post_context_outcome.promoted_response` stays `None`, so
        # `selected_response` below is always `final_response`, exactly as
        # before Phase 9). When enabled *and* every strict promotion gate
        # passes for `graduation_progress_workflow`, the in-memory candidate
        # `AgentResponse` `run_post_context_shadow_compare` captured replaces
        # `final_response` as `selected_response` before finalization — the
        # live deterministic workflow still ran first and is always the
        # fallback. Never used to pick a workflow — only ever swaps which
        # already-computed `AgentResponse` continues down the exact same
        # finalize/persist/emit path below.
        #
        # Phase 14 — Controlled Specialist Text Promotion, layered on the
        # exact same `promoted_response` seam. Independently gated by
        # AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED + _MODE (both default
        # off/"off") and restricted to `graduation_progress_agent` answering
        # `graduation_progress_workflow`; always defers to Phase 9 (skipped
        # whenever Phase 9 already promoted a candidate this turn). When
        # every strict gate passes, `post_context_outcome.promoted_response`
        # is a copy of `final_response` with only `.text` replaced — blocks,
        # warnings, sources, and proposed_actions are always the live
        # workflow's own, unchanged.
        # When Planner-first-live already executed this turn's capability for
        # real, a second, independent Supervisor run purely to "compare live
        # vs shadow" no longer means anything -- there is no separate
        # deterministic response left to compare against. Skip straight to a
        # direct Monitor check against the run this turn already produced
        # (still diagnostic-only: nothing here triggers a live repair yet --
        # that is a later, dedicated phase) instead of re-running the whole
        # graph a second time.
        post_context_outcome = None
        planner_first_live_monitor_metadata: dict[str, Any] | None = None
        if not planner_first_live_used:
            post_context_outcome = await run_post_context_shadow_compare(
                database=database,
                agent_context_pack=context,
                user_message=effective_user_message,
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_id,
                live_workflow_name=task_plan.workflow,
                live_response=final_response,
                planner_output=planner_output.model_dump() if planner_output is not None else None,
                task_understanding_summary=task_understanding_summary,
                deterministic_intent=classification.intent,
                deterministic_entities=entities,
                conversation_entities=conversation.get("entities") or {},
                conversation_assumptions=conversation_assumptions,
                settings=cfg,
            )
        elif cfg.is_agent_monitor_enabled() and planner_first_live_run_output is not None:
            from app.agent.monitoring.diagnostics import build_monitor_metadata
            from app.agent.monitoring.monitor import build_monitor_input_from_shadow_context, monitor_plan_execution

            monitor_input = build_monitor_input_from_shadow_context(
                planner_output=planner_output.model_dump() if planner_output is not None else None,
                shadow_run_output=planner_first_live_run_output,
                task_understanding=task_understanding_summary,
                conversation_assumptions=list(conversation_assumptions or []),
                latest_user_message=user_message,
            )
            monitor_output = monitor_plan_execution(
                monitor_input, enabled=True, dry_run=cfg.is_agent_monitor_dry_run()
            )
            planner_first_live_monitor_metadata = build_monitor_metadata(monitor_output)

        # Phase 4 (post-Phase-9) — close the Monitor->Planner loop, live,
        # within this turn. Independently gated by
        # AGENT_PLANNER_FIRST_LIVE_REPAIR_ENABLED (default off) plus the
        # existing AGENT_PLAN_REPAIR_ENABLED (checked internally by
        # `run_plan_repair_diagnostics`). Only ever attempted once per turn,
        # only when Monitor's decision this turn was literally
        # `request_plan_repair`, and only replaces `final_response` when
        # `attempt_live_plan_repair`'s own narrow safety check passes (see
        # that function and `_is_repaired_plan_safe_to_redispatch` for why
        # this never relies on the permanently-`False`
        # `PlanRepairOutput.safe_to_use`). On any doubt at all this returns
        # `None` and `final_response` is left exactly as Planner-first-live
        # already produced it.
        planner_first_live_repair_metadata: dict[str, Any] | None = None
        if (
            planner_first_live_used
            and cfg.is_agent_planner_first_live_repair_enabled()
            and str((planner_first_live_monitor_metadata or {}).get("decision", {}).get("action") or "")
            == "request_plan_repair"
        ):
            repair_label = "Revising plan"
            if workflow_step_count < cfg.agent_max_workflow_steps:
                workflow_step_count += 1
                yield StreamEvent(type="agent.step.started", label=repair_label, run_id=run_id)
                repaired_candidate, planner_first_live_repair_metadata = await attempt_live_plan_repair(
                    database=database,
                    agent_context_pack=context,
                    user_message=effective_user_message,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    workflow_name=task_plan.workflow,
                    planner_output=planner_output.model_dump() if planner_output is not None else {},
                    monitor_metadata=planner_first_live_monitor_metadata,
                    settings=cfg,
                    allow_single_proposed_action=allow_single_proposed_action,
                )
                yield StreamEvent(type="agent.step.completed", label=repair_label, run_id=run_id)
                if repaired_candidate is not None:
                    final_response = repaired_candidate

        # Phase 5 (post-Phase-9) — Synthesis composes/promotes the live
        # response's text for a Planner-first-live turn, reusing the exact
        # same `run_synthesis_diagnostics`/`evaluate_synthesis_text_promotion`
        # entry points already wired into the deterministic path below (via
        # `post_context_runner`) -- see `attempt_live_synthesis_promotion`
        # for why this is not a new mechanism. Gated entirely by the
        # existing AGENT_SYNTHESIS_ENABLED/AGENT_SYNTHESIS_TEXT_PROMOTION_*
        # settings (both off by default); on any doubt this returns `None`
        # and `final_response` is left exactly as-is.
        # Layer 2 -- Synthesis promotion's `promotion_policy`/comparison logic
        # is written for a single workflow's shape; skip it entirely when
        # this turn's plan actually dispatched more than one capability for
        # real (generalizing it is Synthesis/Composition-layer work, out of
        # scope here). The still-common single-capability case is unaffected.
        planner_first_live_real_capability_names = (
            (planner_first_live_run_output.diagnostics or {}).get("realCapabilityNames")
            if planner_first_live_run_output is not None
            else None
        )
        planner_first_live_single_capability = (
            not isinstance(planner_first_live_real_capability_names, list)
            or len(planner_first_live_real_capability_names) <= 1
        )

        planner_first_live_synthesis_metadata: dict[str, Any] | None = None
        planner_first_live_synthesis_promotion_metadata: dict[str, Any] | None = None
        if planner_first_live_used and final_response is not None and planner_first_live_single_capability:
            (
                promoted_by_synthesis,
                planner_first_live_synthesis_metadata,
                planner_first_live_synthesis_promotion_metadata,
            ) = await attempt_live_synthesis_promotion(
                workflow_name=task_plan.workflow,
                user_message=effective_user_message,
                live_response=final_response,
                monitor_metadata=planner_first_live_monitor_metadata,
                plan_repair_metadata=planner_first_live_repair_metadata,
                settings=cfg,
            )
            if promoted_by_synthesis is not None:
                final_response = promoted_by_synthesis

        # Phase 6 (post-Phase-9) — lets a Planner-first-live turn genuinely
        # pause on a real user-facing clarification question instead of one
        # only ever being available as a post-hoc afterthought. Reuses the
        # exact same `run_clarification_from_shadow_context` entry point
        # the deterministic path already uses; `offer_user_facing_clarification`
        # further below is entirely unchanged -- it already accepts
        # whatever `ClarificationCapabilityOutput` it's handed generically.
        planner_first_live_clarification_metadata: dict[str, Any] | None = None
        planner_first_live_clarification_output = None
        if planner_first_live_used:
            planner_first_live_clarification_output, planner_first_live_clarification_metadata = (
                attempt_live_clarification(
                    planner_output=planner_output.model_dump() if planner_output is not None else {},
                    monitor_metadata=planner_first_live_monitor_metadata,
                    settings=cfg,
                )
            )

        supervisor_validation_metadata = post_context_outcome.validation_metadata if post_context_outcome else None
        supervisor_promotion_metadata = post_context_outcome.promotion_metadata if post_context_outcome else None
        specialist_validation_metadata = (
            post_context_outcome.specialist_validation_metadata if post_context_outcome else None
        )
        specialist_text_promotion_metadata = (
            post_context_outcome.specialist_text_promotion_metadata if post_context_outcome else None
        )
        dynamic_agents_metadata = post_context_outcome.dynamic_agents_metadata if post_context_outcome else None
        monitor_metadata = (
            post_context_outcome.monitor_metadata if post_context_outcome else None
        ) or planner_first_live_monitor_metadata
        clarification_metadata = (
            post_context_outcome.clarification_metadata if post_context_outcome else None
        ) or planner_first_live_clarification_metadata
        clarification_output = (
            post_context_outcome.clarification_output if post_context_outcome else None
        ) or planner_first_live_clarification_output
        plan_repair_metadata = (
            post_context_outcome.plan_repair_metadata if post_context_outcome else None
        ) or planner_first_live_repair_metadata
        synthesis_metadata = (
            post_context_outcome.synthesis_metadata if post_context_outcome else None
        ) or planner_first_live_synthesis_metadata
        synthesis_promotion_metadata = (
            post_context_outcome.synthesis_promotion_metadata if post_context_outcome else None
        ) or planner_first_live_synthesis_promotion_metadata

        from app.agent.readiness.diagnostics import build_turn_runtime_readiness_metadata

        runtime_readiness_metadata = build_turn_runtime_readiness_metadata(
            settings=cfg,
            promotion_diagnostics=[
                synthesis_promotion_metadata,
                specialist_text_promotion_metadata,
                supervisor_promotion_metadata,
            ],
        )

        if planner_diagnostics is not None and (
            planner_diagnostics.get("plannerDynamicAgents") is not None or dynamic_agents_metadata is not None
        ):
            from app.agent.planner.dynamic_spec_diagnostics import merge_planner_dynamic_execution_metadata

            merged_dynamic = merge_planner_dynamic_execution_metadata(
                planner_diagnostics.get("plannerDynamicAgents"),
                dynamic_agents_metadata,
            )
            if merged_dynamic is not None:
                planner_diagnostics = {**planner_diagnostics, "plannerDynamicAgents": merged_dynamic}

        if (
            cfg.is_agent_plan_repair_enabled()
            and plan_repair_metadata is None
            and clarification_state_metadata
            and confirmed_clarification_answers
        ):
            from app.agent.planner.repair_diagnostics import run_plan_repair_diagnostics

            _repair_output, plan_repair_metadata = await run_plan_repair_diagnostics(
                user_goal=effective_user_message,
                planner_output=planner_output.model_dump() if planner_output is not None else None,
                monitor_metadata=monitor_metadata,
                workflow_name=task_plan.workflow,
                intent=classification.intent,
                clarification_state_metadata=clarification_state_metadata,
                confirmed_clarification_answers=confirmed_clarification_answers,
                clarification_assumptions_created=clarification_assumptions_created,
                original_user_message=original_user_message_for_resume,
                current_user_message=user_message,
                settings=cfg,
            )

        selected_response = final_response
        if post_context_outcome is not None and post_context_outcome.promoted_response is not None:
            selected_response = post_context_outcome.promoted_response

        if (
            not skip_clarification_offer
            and cfg.is_agent_clarification_enabled()
            and cfg.is_agent_clarification_user_facing_enabled()
        ):
            from app.agent.clarification.turn_handler import offer_user_facing_clarification

            offer = await offer_user_facing_clarification(
                database,
                conversation_id=conversation_id,
                user_id=user_id,
                run_id=run_id,
                original_user_message=effective_user_message,
                clarification_output=clarification_output,
                live_response=final_response,
                promoted_response=post_context_outcome.promoted_response if post_context_outcome else None,
                task_plan=task_plan,
                classification=classification,
                planner_output=planner_output,
                settings=cfg,
            )
            if offer.response is not None:
                selected_response = offer.response
            if offer.state_metadata is not None:
                clarification_state_metadata = offer.state_metadata

        final_response = await _finalize_response(
            selected_response,
            context=context,
            user_message=effective_user_message,
            cfg=cfg,
        )

        message_id = await _persist_assistant_message(
            database,
            conversation_id=conversation_id,
            user_id=user_id,
            response=final_response,
            run_id=run_id,
            settings=cfg,
        )
        final_response = final_response.model_copy(update={"message_id": message_id})

        async for event in _emit_final_response_events(final_response, run_id=run_id):
            yield event

        run_status = "completed"
        if final_response.proposed_actions:
            run_status = "requires_user_confirmation"

        await complete_agent_run(
            database,
            run_id=run_id,
            user_id=user_id,
            status=run_status,
            intent=classification.intent,
            retrieval_profile=context.retrieval_profile,
            retrieval_metadata=_retrieval_metadata_with_diagnostics(
                context,
                task_understanding_summary,
                capability_diagnostics,
                planner_diagnostics,
                supervisor_diagnostics,
                supervisor_validation_metadata,
                supervisor_promotion_metadata,
                specialist_validation_metadata,
                specialist_text_promotion_metadata,
                dynamic_agents_metadata,
                monitor_metadata,
                clarification_metadata,
                clarification_state_metadata,
                plan_repair_metadata,
                effective_clarification_context,
                synthesis_metadata,
                synthesis_promotion_metadata,
                runtime_readiness_metadata,
                _planner_first_live_metadata(
                    used=planner_first_live_used,
                    workflow_name=task_plan.workflow,
                    run_output=planner_first_live_run_output,
                ),
            ),
            settings=cfg,
        )
        yield StreamEvent(type="run.completed", run_id=run_id, message_id=message_id)

    except Exception as exc:  # noqa: BLE001
        await fail_agent_run(
            database,
            run_id=run_id,
            user_id=user_id,
            error=str(exc),
            settings=cfg,
        )
        yield StreamEvent(type="run.failed", run_id=run_id, error=str(exc))


def _retrieval_metadata_with_diagnostics(
    context: AgentContextPack,
    task_understanding_summary: dict[str, Any] | None,
    capability_diagnostics: dict[str, Any] | None = None,
    planner_diagnostics: dict[str, Any] | None = None,
    supervisor_diagnostics: dict[str, Any] | None = None,
    supervisor_validation_metadata: dict[str, Any] | None = None,
    supervisor_promotion_metadata: dict[str, Any] | None = None,
    specialist_validation_metadata: dict[str, Any] | None = None,
    specialist_text_promotion_metadata: dict[str, Any] | None = None,
    dynamic_agents_metadata: dict[str, Any] | None = None,
    monitor_metadata: dict[str, Any] | None = None,
    clarification_metadata: dict[str, Any] | None = None,
    clarification_state_metadata: dict[str, Any] | None = None,
    plan_repair_metadata: dict[str, Any] | None = None,
    effective_clarification_context: dict[str, Any] | None = None,
    synthesis_metadata: dict[str, Any] | None = None,
    synthesis_promotion_metadata: dict[str, Any] | None = None,
    runtime_readiness_metadata: dict[str, Any] | None = None,
    planner_first_live_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach Phase 3/4/5/6/8/9/11/14/15/16/17/18/19/21/22/25 diagnostic summaries to a copy of `retrievalMetadata`.

    Never mutates `context`. `taskUnderstanding`, `capabilityDiagnostics`,
    `plannerDiagnostics`, `supervisorDiagnostics`, `supervisorValidation`,
    `supervisorPromotion`, `specialistValidation`, `specialistTextPromotion`,
    `dynamicAgents`, `monitorDiagnostics`, `clarificationDiagnostics`,
    `clarificationState`, `planRepairDiagnostics`, `effectiveClarificationContext`,
    `synthesisDiagnostics`, `synthesisPromotion`, and `plannerFirstLive` are
    purely informational — nothing reads them back to influence routing or
    the response.
    """
    metadata = dict(context.retrieval_metadata)
    if task_understanding_summary is not None:
        metadata["taskUnderstanding"] = task_understanding_summary
    if capability_diagnostics is not None:
        metadata["capabilityDiagnostics"] = capability_diagnostics
    if planner_diagnostics is not None:
        metadata["plannerDiagnostics"] = planner_diagnostics
    if supervisor_diagnostics is not None:
        metadata["supervisorDiagnostics"] = supervisor_diagnostics
    if supervisor_validation_metadata is not None:
        metadata["supervisorValidation"] = supervisor_validation_metadata
    if supervisor_promotion_metadata is not None:
        metadata["supervisorPromotion"] = supervisor_promotion_metadata
    if specialist_validation_metadata is not None:
        metadata["specialistValidation"] = specialist_validation_metadata
    if specialist_text_promotion_metadata is not None:
        metadata["specialistTextPromotion"] = specialist_text_promotion_metadata
    if dynamic_agents_metadata is not None:
        metadata["dynamicAgents"] = dynamic_agents_metadata
    if monitor_metadata is not None:
        metadata["monitorDiagnostics"] = monitor_metadata
    if clarification_metadata is not None:
        metadata["clarificationDiagnostics"] = clarification_metadata
    if clarification_state_metadata is not None:
        metadata["clarificationState"] = clarification_state_metadata
    if plan_repair_metadata is not None:
        metadata["planRepairDiagnostics"] = plan_repair_metadata
    if effective_clarification_context is not None:
        metadata["effectiveClarificationContext"] = effective_clarification_context
    if synthesis_metadata is not None:
        metadata["synthesisDiagnostics"] = synthesis_metadata
    if synthesis_promotion_metadata is not None:
        metadata["synthesisPromotion"] = synthesis_promotion_metadata
    if runtime_readiness_metadata is not None:
        metadata["runtimeReadiness"] = runtime_readiness_metadata
    if planner_first_live_metadata is not None:
        metadata["plannerFirstLive"] = planner_first_live_metadata
    return metadata


def _planner_first_live_metadata(
    *,
    used: bool,
    workflow_name: str,
    run_output: Any | None,
) -> dict[str, Any] | None:
    """Compact `plannerFirstLive` diagnostic — `None` when never attempted this turn."""
    if run_output is None and not used:
        return None
    diagnostics = getattr(run_output, "diagnostics", None) or {}
    return {
        "attempted": True,
        "used": used,
        "workflowName": workflow_name,
        "realCapabilityNames": list(diagnostics.get("realCapabilityNames") or []),
        "runStatus": getattr(run_output, "status", None),
        "failedSubtasks": list(getattr(run_output, "failed_subtasks", None) or []),
        "skippedSubtasks": list(getattr(run_output, "skipped_subtasks", None) or []),
    }


async def _finalize_response(
    response: AgentResponse,
    *,
    context: AgentContextPack,
    user_message: str,
    cfg: Settings,
) -> AgentResponse:
    deltas: list[str] = []

    async def on_delta(token: str) -> None:
        deltas.append(token)

    enhanced = await enhance_response_with_llm(
        response,
        context=context,
        user_message=user_message,
        settings=cfg,
        on_delta=on_delta,
    )
    return enhanced


async def _emit_final_response_events(
    response: AgentResponse,
    *,
    run_id: str,
) -> AsyncIterator[StreamEvent]:
    if response.text and len(response.text) > 120:
        chunk_size = 48
        for index in range(0, len(response.text), chunk_size):
            yield StreamEvent(
                type="message.delta",
                text=response.text[index : index + chunk_size],
                run_id=run_id,
            )
    for block in response.blocks:
        yield StreamEvent(type="structured_output", block=block, run_id=run_id)
    for action in response.proposed_actions:
        yield StreamEvent(type="action.proposed", action=action, run_id=run_id)
    yield StreamEvent(
        type="message.completed",
        text=response.text,
        message_id=response.message_id,
        run_id=run_id,
    )


async def _persist_assistant_message(
    database: AsyncIOMotorDatabase,
    *,
    conversation_id: str,
    user_id: str,
    response: AgentResponse,
    run_id: str,
    settings: Settings,
) -> str:
    assistant_message = await create_agent_message(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        role="assistant",
        content=response.text,
        structured_blocks=[block.model_dump() for block in response.blocks],
        run_id=run_id,
        warnings=response.warnings,
        suggested_prompts=response.suggested_prompts,
        proposed_actions=[action.model_dump() for action in response.proposed_actions],
        assumptions=response.assumptions,
        used_sources=response.used_sources,
        settings=settings,
    )
    return str(assistant_message["id"])


async def _record_tool_call(
    database: AsyncIOMotorDatabase,
    *,
    run_id: str,
    user_id: str,
    conversation_id: str,
    tool_name: str,
    input_summary: str | None,
    settings: Settings,
) -> dict[str, Any] | None:
    try:
        return await create_agent_tool_call(
            database,
            run_id=run_id,
            user_id=user_id,
            conversation_id=conversation_id,
            tool_name=tool_name,
            input_summary=input_summary,
            settings=settings,
        )
    except Exception:  # noqa: BLE001 -- tool-call logging must never fail a live turn
        logger.exception("agent_tool_call_record_failed", extra={"runId": run_id, "toolName": tool_name})
        return None


def _clarification_response(context: AgentContextPack) -> AgentResponse | None:
    blocking = [error for error in context.validation.errors if error]
    if not blocking:
        return None

    if any("profile" in error.lower() for error in blocking):
        text = (
            "I need your student profile before I can answer this accurately. "
            "Please complete your degree program, track, and catalog year on your profile."
        )
    elif any("course number" in error.lower() for error in blocking):
        text = "Which course number are you asking about? Please provide the Technion course number."
    elif any("transcript" in error.lower() or "upload" in error.lower() for error in blocking):
        text = (
            "Please upload your official transcript PDF with your message. "
            "I will parse it and show a review table before saving any courses."
        )
    elif any("semester" in error.lower() for error in blocking):
        text = (
            "Which semester should I plan for? Say 'next semester' or provide a semester code like 2025-2."
        )
    else:
        text = "I need a bit more information before I can continue: " + "; ".join(blocking)

    warning_block = StructuredBlock(
        type="WarningBlock",
        data={"messages": blocking, "validationStatus": context.validation.status},
    )
    source_block = StructuredBlock(
        type="SourceSummaryBlock",
        data={"provenance": context.provenance, "usedSources": context.provenance[:5]},
    )
    return compose_response(
        conversation_id=context.conversation_id,
        message_id="",
        run_id=context.run_id,
        text=text,
        blocks=[warning_block, source_block],
        warnings=list(context.validation.warnings),
        assumptions=list(context.missing_data),
        used_sources=list(context.provenance),
    )
