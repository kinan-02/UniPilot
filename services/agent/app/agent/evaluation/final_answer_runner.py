"""Eval-safe runner that invokes the agent and captures final answer text."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Literal

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.evaluation.agent_setup import GOLDEN_ANSWER_EVAL_SETUP, setup_eval_user
from app.agent.evaluation.eval_llm_tracker import EvalLlmCallTracker, eval_llm_tracker_context
from app.agent.evaluation.eval_timing import CaseTiming, extract_phase_timing_from_metadata
from app.agent.evaluation.final_answer_eval import (
    FinalAnswerCaseResult,
    GoldenAnswerCase,
    JudgeMode,
    evaluate_fact_deterministic,
    score_final_answer_case,
)
from app.agent.evaluation.side_effect_firewall import EvalSideEffectFirewall, SideEffectViolation
from app.agent.evaluation.trace_extraction import populate_trace_from_turn
from app.agent.evaluation.trace_logging import (
    EvalCaseTrace,
    EvalTraceCollector,
    TraceConfig,
    validate_trace_dir,
    validate_unsafe_raw_llm_mode,
)
from app.agent.evaluation.trace_run_loader import load_turn_trace_context
from app.agent.orchestrator import run_agent_turn
from app.agent.reasoning.debug_observer import EvalRawLlmDebugSink, eval_debug_observer_context
from app.agent.schemas import StreamEvent
from app.config import Settings, get_settings
from app.repositories.agent_message_repository import create_agent_message, list_messages_for_conversation
from app.repositories.agent_conversation_repository import update_conversation_preview

logger = logging.getLogger(__name__)

RunnerMode = Literal["local_agent"]
AgentEvalMode = Literal["full_live", "deterministic_fast"]


def _lab_settings_from_payload(
    payload: dict[str, Any],
    *,
    base: Settings | None = None,
) -> Settings:
    """Apply lab overrides; constructed values beat process env (via model_construct)."""
    merged = dict(base.model_dump()) if base is not None else {}
    applied = Settings(_env_file=None, **payload).model_dump()
    merged.update(applied)
    return Settings.model_construct(**merged)


@dataclass
class AgentTurnCapture:
    final_answer: str
    used_sources: list[str]
    run_failed: bool
    run_error: str | None
    latency_ms: float
    firewall_violations: list[dict[str, str]]
    sse_events: list[dict[str, Any]]
    intent: str | None = None
    llm_call_count: int = 0
    llm_total_ms: float = 0.0
    retrieval_metadata: dict[str, Any] | None = None


def build_final_answer_eval_settings(
    *,
    base: Settings | None = None,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """Lab settings for golden-set final answer evaluation."""
    payload: dict[str, Any] = {
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "shadow_only",
        "AGENT_CLARIFICATION_STATE_ENABLED": False,
        "AGENT_CLARIFICATION_USER_FACING_ENABLED": True,
        "AGENT_EVAL_SIDE_EFFECT_FIREWALL_ENABLED": True,
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
        # Keep rules-first intent routing; LLM fallback often returns
        # unknown_or_unsupported and routes to the generic fallback answer.
        "AGENT_LLM_INTENT_FALLBACK_ENABLED": False,
        "AGENT_LLM_EXPLANATION_ENABLED": True,
        # Task Understanding runs for eval traces, but `AGENT_TASK_UNDERSTANDING_DRY_RUN`
        # is left at its default (True) here, so it stays diagnostic-only for this
        # config (routing still follows AGENT_LLM_INTENT_FALLBACK_ENABLED above) —
        # set AGENT_TASK_UNDERSTANDING_DRY_RUN=False explicitly to exercise the
        # authoritative path (see app/agent/task_understanding/integration.py).
        "AGENT_TASK_UNDERSTANDING_ENABLED": True,
        "AGENT_PLANNER_ENABLED": True,
        "AGENT_PLANNER_DRY_RUN": True,
        "AGENT_SUPERVISOR_ENABLED": True,
        "AGENT_SUPERVISOR_DRY_RUN": True,
    }
    if overrides:
        payload.update(overrides)
    return _lab_settings_from_payload(payload, base=base)


def build_full_architecture_eval_settings(
    *,
    base: Settings | None = None,
    overrides: dict[str, Any] | None = None,
) -> Settings:
    """Full MAS stack lab settings: all reasoning phases + post-context shadow compare.

    Uses the live orchestrator path (`run_agent_turn` → context_builder → workflow)
    with every Phase 3–22 diagnostic/promotion layer enabled for real LLM calls.
    Side-effect firewall stays on for eval safety.
    """
    from app.agent.evaluation.full_shadow_runner import build_full_llm_shadow_lab_settings

    payload: dict[str, Any] = {
        "AGENT_GRAPH_RETRIEVAL_ENABLED": True,
        "AGENT_SPECIALIST_AGENTS_ENABLED": True,
        "AGENT_SPECIALIST_AGENTS_DRY_RUN": True,
        "AGENT_LLM_INTENT_FALLBACK_ENABLED": False,
        "AGENT_LLM_EXPLANATION_ENABLED": True,
        "AGENT_CLARIFICATION_USER_FACING_ENABLED": True,
        "AGENT_EVAL_SIDE_EFFECT_FIREWALL_ENABLED": True,
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
    }
    shadow_dump = build_full_llm_shadow_lab_settings().model_dump()
    payload.update(
        {
            "AGENT_TASK_UNDERSTANDING_ENABLED": shadow_dump["agent_task_understanding_enabled"],
            "AGENT_PLANNER_ENABLED": shadow_dump["agent_planner_enabled"],
            "AGENT_PLANNER_DRY_RUN": shadow_dump["agent_planner_dry_run"],
            "AGENT_PLANNER_DYNAMIC_SPECS_ENABLED": shadow_dump["agent_planner_dynamic_specs_enabled"],
            "AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN": shadow_dump["agent_planner_dynamic_specs_dry_run"],
            "AGENT_SUPERVISOR_ENABLED": shadow_dump["agent_supervisor_enabled"],
            "AGENT_SUPERVISOR_DRY_RUN": shadow_dump["agent_supervisor_dry_run"],
            "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": shadow_dump[
                "agent_supervisor_post_context_compare_enabled"
            ],
            "AGENT_DYNAMIC_AGENTS_ENABLED": shadow_dump["agent_dynamic_agents_enabled"],
            "AGENT_DYNAMIC_AGENTS_DRY_RUN": shadow_dump["agent_dynamic_agents_dry_run"],
            "AGENT_MONITOR_ENABLED": shadow_dump["agent_monitor_enabled"],
            "AGENT_MONITOR_DRY_RUN": shadow_dump["agent_monitor_dry_run"],
            "AGENT_CLARIFICATION_ENABLED": shadow_dump["agent_clarification_enabled"],
            "AGENT_PLAN_REPAIR_ENABLED": shadow_dump["agent_plan_repair_enabled"],
            "AGENT_PLAN_REPAIR_DRY_RUN": shadow_dump["agent_plan_repair_dry_run"],
            "AGENT_PLAN_REPAIR_USE_LLM": shadow_dump["agent_plan_repair_use_llm"],
            "AGENT_SYNTHESIS_ENABLED": shadow_dump["agent_synthesis_enabled"],
            "AGENT_SYNTHESIS_DRY_RUN": shadow_dump["agent_synthesis_dry_run"],
            "AGENT_SYNTHESIS_USE_LLM": shadow_dump["agent_synthesis_use_llm"],
            "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": shadow_dump["agent_synthesis_text_promotion_enabled"],
            "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": shadow_dump["agent_synthesis_text_promotion_mode_raw"],
        }
    )
    if overrides:
        payload.update(overrides)
    return _lab_settings_from_payload(payload, base=base)


async def _collect_agent_turn(
    database: AsyncIOMotorDatabase,
    *,
    user_id: str,
    conversation_id: str,
    message: str,
    settings: Settings,
    firewall: EvalSideEffectFirewall | None = None,
    trace_collector: EvalTraceCollector | None = None,
    raw_debug_sink: EvalRawLlmDebugSink | None = None,
) -> AgentTurnCapture:
    started = time.perf_counter()
    final_text = ""
    run_failed = False
    run_error: str | None = None
    firewall_violations: list[dict[str, str]] = []
    sse_events: list[dict[str, Any]] = []
    intent: str | None = None

    user_message = await create_agent_message(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        role="user",
        content=message.strip(),
        settings=settings,
    )
    await update_conversation_preview(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        preview=message.strip(),
    )

    active_firewall = firewall or EvalSideEffectFirewall()
    active_firewall.install()
    llm_tracker = EvalLlmCallTracker(case_id=trace_collector.case.id if trace_collector else "eval")
    observer = raw_debug_sink if raw_debug_sink is not None else llm_tracker
    try:
        with eval_llm_tracker_context(llm_tracker):
            with eval_debug_observer_context(
                observer,
                case_id=trace_collector.case.id if trace_collector else "eval",
                phase="agent_turn",
            ):
                async for event in run_agent_turn(
                    database,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    user_message=message.strip(),
                    trigger_message_id=str(user_message["id"]),
                    settings=settings,
                ):
                    payload = _event_to_dict(event)
                    sse_events.append(payload)
                    if payload.get("type") == "message.completed":
                        final_text = str(payload.get("text") or final_text)
                    if payload.get("type") == "run.failed":
                        run_failed = True
                        run_error = str(payload.get("error") or "Agent run failed")
    except SideEffectViolation as exc:
        run_failed = True
        run_error = str(exc)
        firewall_violations = active_firewall.violations()
    finally:
        active_firewall.uninstall()

    used_sources: list[str] = []
    messages = await list_messages_for_conversation(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
    )
    for item in reversed(messages):
        if item.get("role") != "assistant":
            continue
        used_sources = [str(source) for source in (item.get("usedSources") or [])]
        if not final_text:
            final_text = str(item.get("content") or "")
        break

    latency_ms = (time.perf_counter() - started) * 1000.0
    retrieval_metadata, entities = await load_turn_trace_context(
        database,
        conversation_id=conversation_id,
        user_id=user_id,
        settings=settings,
    )
    intent = str((retrieval_metadata or {}).get("intent") or "") or None

    if trace_collector is not None:
        populate_trace_from_turn(
            trace_collector,
            sse_events=sse_events,
            retrieval_metadata=retrieval_metadata,
            intent=intent,
            entities=entities,
            used_sources=used_sources,
            firewall_violations=firewall_violations,
            latency_ms=latency_ms,
        )

    return AgentTurnCapture(
        final_answer=final_text,
        used_sources=used_sources,
        run_failed=run_failed,
        run_error=run_error,
        latency_ms=latency_ms,
        firewall_violations=firewall_violations,
        sse_events=sse_events,
        intent=intent,
        llm_call_count=llm_tracker.call_count,
        llm_total_ms=llm_tracker.total_duration_ms,
        retrieval_metadata=retrieval_metadata if isinstance(retrieval_metadata, dict) else None,
    )


def _event_to_dict(event: StreamEvent | dict[str, Any]) -> dict[str, Any]:
    if isinstance(event, StreamEvent):
        return event.to_sse_payload()
    return dict(event)


async def run_final_answer_eval_case(
    database: AsyncIOMotorDatabase | None,
    case: GoldenAnswerCase,
    *,
    allow_real_llm: bool = False,
    judge_mode: JudgeMode = "deterministic",
    settings_overrides: dict[str, Any] | None = None,
    full_architecture: bool = False,
    firewall: EvalSideEffectFirewall | None = None,
    trace_config: TraceConfig | None = None,
    agent_mode: AgentEvalMode = "full_live",
    require_mongo: bool = False,
    fallback_to_full_live: bool = False,
) -> tuple[FinalAnswerCaseResult, EvalCaseTrace | None, CaseTiming]:
    """Run one golden-set case and score the final answer."""
    timing = CaseTiming(case_id=case.id, agent_mode=agent_mode)
    case_started = time.perf_counter()

    if agent_mode == "deterministic_fast":
        from app.agent.evaluation.deterministic_fast_runner import run_deterministic_fast_eval_case

        result, case_trace, fast_timing = await run_deterministic_fast_eval_case(
            database,
            case,
            judge_mode=judge_mode,
            require_mongo=require_mongo,
            trace_config=trace_config,
        )
        fast_timing.case_id = case.id
        if result.failures == ["deterministic_fast_unsupported"] and fallback_to_full_live and allow_real_llm:
            if database is None:
                timing.total_ms = (time.perf_counter() - case_started) * 1000.0
                return result, case_trace, timing
            return await run_final_answer_eval_case(
                database,
                case,
                allow_real_llm=allow_real_llm,
                judge_mode=judge_mode,
                settings_overrides=settings_overrides,
                full_architecture=full_architecture,
                firewall=firewall,
                trace_config=trace_config,
                agent_mode="full_live",
                require_mongo=require_mongo,
                fallback_to_full_live=False,
            )
        return result, case_trace, fast_timing

    if not allow_real_llm:
        raise ValueError("final_answer_eval_requires_allow_real_llm")
    if database is None:
        raise ValueError("full_live_eval_requires_mongo")

    trace_collector: EvalTraceCollector | None = None
    raw_debug_sink: EvalRawLlmDebugSink | None = None
    effective_trace_dir = None
    if trace_config is not None:
        effective_trace_dir = trace_config.trace_failure_dir if trace_config.trace_on_failure else trace_config.trace_dir
        if effective_trace_dir is not None:
            validate_trace_dir(effective_trace_dir)
        if trace_config.unsafe_local_raw_llm_logs and effective_trace_dir is not None:
            validate_unsafe_raw_llm_mode(
                trace_dir=effective_trace_dir,
                enabled=trace_config.unsafe_local_raw_llm_logs,
            )
            raw_debug_sink = EvalRawLlmDebugSink(
                trace_dir=effective_trace_dir,
                case_id=case.id,
                max_chars=trace_config.raw_llm_log_max_chars,
            )
        if effective_trace_dir is not None or trace_config.include_trace_events_in_report:
            trace_collector = EvalTraceCollector(case=case, config=trace_config)

    settings_builder = (
        build_full_architecture_eval_settings
        if full_architecture
        else build_final_answer_eval_settings
    )
    settings = settings_builder(base=get_settings(), overrides=settings_overrides)

    setup_started = time.perf_counter()
    setup = await setup_eval_user(
        database,
        case_id=case.id,
        setup=GOLDEN_ANSWER_EVAL_SETUP,
    )
    timing.eval_setup_ms = (time.perf_counter() - setup_started) * 1000.0
    timing.mongo_ms += timing.eval_setup_ms
    if not setup.ok or setup.context is None:
        timing.total_ms = (time.perf_counter() - case_started) * 1000.0
        result = FinalAnswerCaseResult(
            case_id=case.id,
            status="errored",
            query_type=case.query_type,
            difficulty=case.difficulty,
            user_request=case.user_request,
            final_answer="",
            failures=["setup_failed"],
            warnings=[setup.skip_reason or "setup_failed"],
        )
        case_trace = trace_collector.build_case_trace(result) if trace_collector else None
        return result, case_trace, timing

    context = setup.context
    try:
        turn = await _collect_agent_turn(
            database,
            user_id=context.user_id,
            conversation_id=context.conversation_id,
            message=case.user_request,
            settings=settings,
            firewall=firewall,
            trace_collector=trace_collector,
            raw_debug_sink=raw_debug_sink,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("final_answer_eval_case_failed", extra={"caseId": case.id})
        timing.total_ms = (time.perf_counter() - case_started) * 1000.0
        result = FinalAnswerCaseResult(
            case_id=case.id,
            status="errored",
            query_type=case.query_type,
            difficulty=case.difficulty,
            user_request=case.user_request,
            final_answer="",
            failures=[type(exc).__name__],
            warnings=[str(exc)[:240]],
        )
        case_trace = trace_collector.build_case_trace(result) if trace_collector else None
        return result, case_trace, timing

    timing.agent_turn_ms = turn.latency_ms
    timing.llm_call_count = turn.llm_call_count
    timing.llm_total_ms = turn.llm_total_ms
    for key, value in extract_phase_timing_from_metadata(turn.retrieval_metadata).items():
        setattr(timing, key, value)

    if turn.run_failed:
        timing.total_ms = (time.perf_counter() - case_started) * 1000.0
        result = FinalAnswerCaseResult(
            case_id=case.id,
            status="errored",
            query_type=case.query_type,
            difficulty=case.difficulty,
            user_request=case.user_request,
            final_answer=turn.final_answer,
            failures=["agent_run_failed"],
            warnings=[turn.run_error or "agent_run_failed"],
        )
        case_trace = trace_collector.build_case_trace(result) if trace_collector else None
        return result, case_trace, timing

    fact_started = time.perf_counter()
    from app.agent.evaluation.final_answer_judge import evaluate_facts_with_judge

    fact_results, hallucination_warnings = await evaluate_facts_with_judge(
        case=case,
        final_answer=turn.final_answer,
        judge_mode=judge_mode,
        settings=settings,
        allow_real_llm=allow_real_llm,
    )
    timing.fact_evaluation_ms = (time.perf_counter() - fact_started) * 1000.0

    result = score_final_answer_case(
        case,
        final_answer=turn.final_answer,
        fact_results=fact_results,
        used_sources=turn.used_sources,
        hallucination_warnings=hallucination_warnings,
    )
    if turn.firewall_violations:
        result.warnings.extend(
            [f"firewall:{item.get('kind')}:{item.get('target')}" for item in turn.firewall_violations]
        )
    case_trace = trace_collector.build_case_trace(result) if trace_collector else None
    if trace_collector is not None:
        trace_collector.add_event(
            phase="evaluation",
            event_type="fact_check",
            name="deterministic_golden_set",
            status=result.status,
            data={
                "factCoverage": result.fact_coverage,
                "factsPresent": result.facts_present,
                "factsPartial": result.facts_partial,
                "factsMissing": result.facts_missing,
                "factsContradicted": result.facts_contradicted,
                "missingFacts": [item.fact for item in result.fact_results if item.status == "missing"][:20],
                "contradictedFacts": [
                    item.fact for item in result.fact_results if item.status == "contradicted"
                ][:20],
                "failures": result.failures,
                "warnings": result.warnings,
            },
        )
        case_trace = trace_collector.build_case_trace(result)

    timing.total_ms = (time.perf_counter() - case_started) * 1000.0
    return result, case_trace, timing


async def evaluate_final_answer_only(
    case: GoldenAnswerCase,
    *,
    final_answer: str,
    used_sources: list[str] | None = None,
    judge_mode: JudgeMode = "deterministic",
    allow_real_llm: bool = False,
    settings: Settings | None = None,
) -> FinalAnswerCaseResult:
    """Score a provided final answer without invoking the agent (tests / offline)."""
    from app.agent.evaluation.final_answer_judge import evaluate_facts_with_judge

    fact_results, hallucination_warnings = await evaluate_facts_with_judge(
        case=case,
        final_answer=final_answer,
        judge_mode=judge_mode,
        settings=settings or get_settings(),
        allow_real_llm=allow_real_llm,
    )
    return score_final_answer_case(
        case,
        final_answer=final_answer,
        fact_results=fact_results,
        used_sources=used_sources,
        hallucination_warnings=hallucination_warnings,
    )
