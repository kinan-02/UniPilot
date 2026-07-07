"""Deterministic-fast final answer eval path (Phase 28.1).

Skips live LLM task understanding, planner, and orchestrator when wiki-grounded
deterministic composition is available.
"""

from __future__ import annotations

import time
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agent.entity_resolver import resolve_entities
from app.agent.evaluation.agent_setup import setup_eval_user
from app.agent.evaluation.eval_timing import CaseTiming
from app.agent.evaluation.final_answer_eval import (
    FinalAnswerCaseResult,
    GoldenAnswerCase,
    JudgeMode,
    score_final_answer_case,
)
from app.agent.evaluation.agent_setup import GOLDEN_ANSWER_EVAL_SETUP, setup_eval_user
from app.agent.evaluation.trace_logging import EvalCaseTrace, EvalTraceCollector, TraceConfig
from app.services.academic_lookup_service import detect_academic_query_kind
from app.services.academic_lookup_service import try_compose_deterministic_answer
from app.services.prerequisite_validation_service import (
    ELIGIBILITY_VALIDATION_SOURCE,
    compose_eligibility_answer,
    validate_course_prerequisites,
)

_DETERMINISTIC_KINDS = frozenset(
    {
        "course_catalog_prerequisites",
        "course_tracks_requiring",
        "course_compound_catalog",
        "course_eligibility",
        "track_credit_breakdown",
        "regulation_moed_grade",
        "regulation_standing_list",
    }
)


def deterministic_fast_supported(user_message: str, *, entities: dict[str, Any] | None = None) -> bool:
    kind = detect_academic_query_kind(user_message)
    if kind in _DETERMINISTIC_KINDS:
        if kind == "course_eligibility":
            return bool((entities or resolve_entities(user_message)).get("courseNumber"))
        if kind == "track_credit_breakdown":
            resolved = dict(entities or resolve_entities(user_message))
            return bool(resolved.get("trackSlug") or resolved.get("trackCode"))
        if kind.startswith("course_"):
            return bool((entities or resolve_entities(user_message)).get("courseNumber"))
        return True
    preview = try_compose_deterministic_answer(user_message, entities=entities or resolve_entities(user_message))
    return preview is not None


async def compose_deterministic_fast_answer(
    database: AsyncIOMotorDatabase | None,
    *,
    case: GoldenAnswerCase,
    setup_completed_courses: list[str] | None = None,
    completed_data_available: bool = False,
) -> tuple[str, list[str], list[str]]:
    """Return final answer text, used sources, and warnings."""
    entities = resolve_entities(case.user_request)
    kind = detect_academic_query_kind(case.user_request)
    warnings: list[str] = []

    if kind == "course_eligibility":
        course_number = str(entities.get("courseNumber") or "").strip()
        if not course_number:
            raise ValueError("deterministic_fast_missing_course_number")
        validation = validate_course_prerequisites(
            course_number,
            completed_course_codes=list(setup_completed_courses or []),
            completed_data_available=completed_data_available,
        )
        headline, _verdict = compose_eligibility_answer(validation)
        sources = list(validation.source_paths)
        if ELIGIBILITY_VALIDATION_SOURCE not in sources:
            sources.append(ELIGIBILITY_VALIDATION_SOURCE)
        return headline, sources, warnings

    composed = try_compose_deterministic_answer(case.user_request, entities=entities)
    if composed is None:
        raise ValueError("deterministic_fast_unsupported")
    text, sources = composed
    return text, list(sources), warnings


async def run_deterministic_fast_eval_case(
    database: AsyncIOMotorDatabase | None,
    case: GoldenAnswerCase,
    *,
    judge_mode: JudgeMode = "deterministic",
    require_mongo: bool = False,
    trace_config: TraceConfig | None = None,
) -> tuple[FinalAnswerCaseResult, EvalCaseTrace | None, CaseTiming]:
    timing = CaseTiming(agent_mode="deterministic_fast")
    case_started = time.perf_counter()
    trace_collector = EvalTraceCollector(case=case, config=trace_config) if trace_config else None

    entities = resolve_entities(case.user_request)
    if not deterministic_fast_supported(case.user_request, entities=entities):
        timing.total_ms = (time.perf_counter() - case_started) * 1000.0
        result = FinalAnswerCaseResult(
            case_id=case.id,
            status="errored",
            query_type=case.query_type,
            difficulty=case.difficulty,
            user_request=case.user_request,
            final_answer="",
            failures=["deterministic_fast_unsupported"],
            warnings=["deterministic_fast_unsupported"],
        )
        case_trace = trace_collector.build_case_trace(result) if trace_collector else None
        return result, case_trace, timing

    setup_started = time.perf_counter()
    completed_courses: list[str] = []
    completed_data_available = False
    kind = detect_academic_query_kind(case.user_request)

    if kind == "course_eligibility":
        if database is None:
            timing.total_ms = (time.perf_counter() - case_started) * 1000.0
            result = FinalAnswerCaseResult(
                case_id=case.id,
                status="errored",
                query_type=case.query_type,
                difficulty=case.difficulty,
                user_request=case.user_request,
                final_answer="",
                failures=["mongo_required_for_eligibility"],
                warnings=["mongo_required_for_eligibility"],
            )
            case_trace = trace_collector.build_case_trace(result) if trace_collector else None
            return result, case_trace, timing

        setup = await setup_eval_user(
            database,
            case_id=case.id,
            setup=GOLDEN_ANSWER_EVAL_SETUP,
        )
        timing.eval_setup_ms = (time.perf_counter() - setup_started) * 1000.0
        timing.mongo_ms += timing.eval_setup_ms
        if not setup.ok:
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
        completed_courses = list(setup.context.seeded_courses if setup.context else [])
        completed_data_available = True
    elif require_mongo and database is not None:
        # Optional isolated namespace even for read-only deterministic cases.
        setup = await setup_eval_user(database, case_id=case.id, setup={"profileTemplate": None})
        timing.eval_setup_ms = (time.perf_counter() - setup_started) * 1000.0
        timing.mongo_ms += timing.eval_setup_ms
    else:
        timing.eval_setup_ms = (time.perf_counter() - setup_started) * 1000.0

    turn_started = time.perf_counter()
    try:
        final_answer, used_sources, compose_warnings = await compose_deterministic_fast_answer(
            database,
            case=case,
            setup_completed_courses=completed_courses,
            completed_data_available=completed_data_available,
        )
    except ValueError as exc:
        timing.agent_turn_ms = (time.perf_counter() - turn_started) * 1000.0
        timing.total_ms = (time.perf_counter() - case_started) * 1000.0
        code = str(exc)
        result = FinalAnswerCaseResult(
            case_id=case.id,
            status="errored",
            query_type=case.query_type,
            difficulty=case.difficulty,
            user_request=case.user_request,
            final_answer="",
            failures=[code],
            warnings=[code],
        )
        case_trace = trace_collector.build_case_trace(result) if trace_collector else None
        return result, case_trace, timing

    timing.agent_turn_ms = (time.perf_counter() - turn_started) * 1000.0
    timing.workflow_ms = timing.agent_turn_ms
    timing.llm_call_count = 0
    timing.llm_total_ms = 0.0

    if trace_collector is not None:
        trace_collector.add_event(
            phase="deterministic_fast",
            event_type="compose",
            name="academic_lookup_service",
            status="completed",
            data={
                "queryKind": kind,
                "llmCallCount": 0,
                "usedSources": used_sources[:12],
            },
        )

    fact_started = time.perf_counter()
    from app.agent.evaluation.final_answer_judge import evaluate_facts_with_judge

    fact_results, hallucination_warnings = await evaluate_facts_with_judge(
        case=case,
        final_answer=final_answer,
        judge_mode=judge_mode,
        settings=None,
        allow_real_llm=False,
    )
    timing.fact_evaluation_ms = (time.perf_counter() - fact_started) * 1000.0

    result = score_final_answer_case(
        case,
        final_answer=final_answer,
        fact_results=fact_results,
        used_sources=used_sources,
        hallucination_warnings=hallucination_warnings,
    )
    if compose_warnings:
        result.warnings.extend(compose_warnings)

    timing.total_ms = (time.perf_counter() - case_started) * 1000.0
    case_trace = trace_collector.build_case_trace(result) if trace_collector else None
    return result, case_trace, timing
