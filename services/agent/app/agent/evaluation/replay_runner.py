"""Offline replay runner for autonomous agent eval (Phase 23 + Phase 26)."""

from __future__ import annotations

import logging
from typing import Any, Literal

from app.agent.evaluation.full_shadow_runner import run_full_llm_shadow_eval_case
from app.agent.evaluation.gates_eval import build_observed_from_case, evaluate_case_result
from app.agent.evaluation.fake_reasoning import FakeReasoningBlockRunner
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult, EvalMode
from app.agent.schemas import AgentResponse, StructuredBlock
from app.config import Settings, get_settings
from app.retrieval.evaluation.progress import NullProgress, ProgressReporter

logger = logging.getLogger(__name__)


def _build_live_response(case: EvalCase) -> AgentResponse:
    live = case.live_response_summary
    blocks: list[StructuredBlock] = []
    if int(live.get("blockCount") or 0) > 0:
        blocks = [StructuredBlock(type="EvalSummaryBlock", data={"caseId": case.id})]
    return AgentResponse(
        conversation_id="eval",
        message_id="eval",
        run_id="eval",
        text=str(live.get("textPreview") or "eval response"),
        blocks=blocks,
        warnings=list(live.get("warnings") or []) if isinstance(live.get("warnings"), list) else [],
        proposed_actions=[],
        used_sources=list(live.get("usedSources") or []) if isinstance(live.get("usedSources"), list) else [],
    )


async def _shadow_replay_metadata(case: EvalCase, *, allow_real_llm: bool) -> dict[str, Any]:
    """Conservative partial replay of internal promotion/policy gates."""
    if allow_real_llm:
        raise ValueError("real_llm_not_supported_in_shadow_replay")

    replay: dict[str, Any] = {}

    if case.mock_reasoning_outputs:
        runner = FakeReasoningBlockRunner(case.mock_reasoning_outputs)
        from app.agent.reasoning.schemas import ReasoningBlockInput

        for mock in case.mock_reasoning_outputs:
            await runner.run(
                ReasoningBlockInput(
                    block_id=f"eval-{case.id}",
                    agent_name="eval",
                    objective="offline eval mock",
                    task_context={"caseId": case.id},
                    output_schema_name=mock.contract_name,
                    output_schema={"type": "object"},
                    prompt_contract_name=mock.contract_name,
                )
            )

    meta = dict(case.retrieval_metadata)
    synthesis_output_present = bool(meta.get("synthesisDiagnostics"))
    if synthesis_output_present or case.expected.expected_synthesis_promotion != "not_applicable":
        try:
            from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata
            from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
            from app.agent.synthesis.schemas import SynthesisOutput

            synthesis_diag = meta.get("synthesisDiagnostics") or {}
            synthesis_output = SynthesisOutput(
                status=synthesis_diag.get("status") or "skipped",  # type: ignore[arg-type]
                synthesis_id=f"eval-{case.id}",
                decision_summary="shadow replay",
                candidate_answer_text=str(case.live_response_summary.get("textPreview") or "eval"),
                safe_to_show=bool(synthesis_diag.get("safeToShow")),
                safe_to_promote=False,
                confidence=float(synthesis_diag.get("confidence") or 0.0),
            )
            settings = Settings(
                AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED=True,
                AGENT_SYNTHESIS_TEXT_PROMOTION_MODE="promote_validated",
                AGENT_SYNTHESIS_ENABLED=True,
            )
            decision = evaluate_synthesis_text_promotion(
                workflow_name=str(case.compact_context.get("workflow") or case.expected.expected_workflow or ""),
                live_response=_build_live_response(case),
                synthesis_output=synthesis_output,
                retrieval_metadata=meta,
                settings=settings,
                existing_promotion_already_applied=bool((meta.get("supervisorPromotion") or {}).get("promoted")),
                workflow_promotion_already_applied=bool((meta.get("supervisorPromotion") or {}).get("promoted")),
                specialist_text_promotion_already_applied=bool((meta.get("specialistTextPromotion") or {}).get("promoted")),
            )
            replay["synthesisPromotion"] = build_synthesis_promotion_metadata(decision)
        except Exception as exc:  # noqa: BLE001
            logger.debug("shadow_replay_synthesis_failed", exc_info=exc)
            replay["synthesisPromotion"] = {"status": "error", "promoted": False, "warnings": [type(exc).__name__]}

    return replay


def _validate_full_llm_shadow_request(*, mode: EvalMode, allow_real_llm: bool, settings: Settings | None = None) -> None:
    cfg = settings or get_settings()
    if mode != "full_llm_shadow_replay":
        return
    if cfg.is_agent_eval_full_llm_require_explicit_allow() and not allow_real_llm:
        raise ValueError("full_llm_shadow_replay_requires_allow_real_llm")


async def run_eval_case(
    case: EvalCase,
    *,
    mode: EvalMode = "gates_only",
    allow_real_llm: bool = False,
    max_reasoning_calls: int | None = None,
    settings_overrides: dict[str, Any] | None = None,
) -> EvalCaseResult:
    """Run one eval case offline. Never writes student data or calls real LLM by default."""
    try:
        settings = get_settings()
        _validate_full_llm_shadow_request(mode=mode, allow_real_llm=allow_real_llm, settings=settings)

        if mode == "full_llm_shadow_replay":
            per_case_limit = max_reasoning_calls or settings.resolved_agent_eval_full_llm_max_reasoning_calls_per_case()
            return await run_full_llm_shadow_eval_case(
                case,
                allow_real_llm=allow_real_llm,
                max_reasoning_calls=per_case_limit,
                settings_overrides=settings_overrides,
            )

        if allow_real_llm and mode != "full_llm_shadow_replay":
            return EvalCaseResult(
                case_id=case.id,
                name=case.name,
                status="error",
                failures=["real_llm_not_supported"],
            )

        replay_meta: dict[str, Any] | None = None
        if mode == "shadow_replay":
            replay_meta = await _shadow_replay_metadata(case, allow_real_llm=allow_real_llm)

        observed = build_observed_from_case(case, replay_observed=replay_meta)
        return evaluate_case_result(case=case, observed=observed)
    except ValueError as exc:
        return EvalCaseResult(
            case_id=case.id,
            name=case.name,
            status="error",
            failures=[str(exc)],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("eval_case_failed", extra={"caseId": case.id})
        return EvalCaseResult(
            case_id=case.id,
            name=case.name,
            status="error",
            failures=[f"eval_error:{type(exc).__name__}"],
        )


def _sync_progress_total(reporter: ProgressReporter, total: int) -> None:
    set_total = getattr(reporter, "set_total", None)
    if callable(set_total):
        set_total(total)


async def run_eval_cases(
    cases: list[EvalCase],
    *,
    mode: EvalMode = "gates_only",
    allow_real_llm: bool = False,
    max_cases: int | None = None,
    max_reasoning_calls: int | None = None,
    max_total_reasoning_calls: int | None = None,
    settings_overrides: dict[str, Any] | None = None,
    progress: ProgressReporter | None = None,
) -> list[EvalCaseResult]:
    settings = get_settings()
    _validate_full_llm_shadow_request(mode=mode, allow_real_llm=allow_real_llm, settings=settings)

    selected = cases
    if max_cases is not None:
        selected = cases[: max(0, max_cases)]
    elif mode == "full_llm_shadow_replay":
        selected = cases[: settings.resolved_agent_eval_full_llm_max_cases()]

    reporter = progress or NullProgress()
    _sync_progress_total(reporter, len(selected))
    reporter.set_phase(f"Agent replay ({mode})")

    results: list[EvalCaseResult] = []
    total_calls = 0
    total_limit = max_total_reasoning_calls or settings.resolved_agent_eval_full_llm_max_total_reasoning_calls()
    per_case_limit = max_reasoning_calls or settings.resolved_agent_eval_full_llm_max_reasoning_calls_per_case()

    for index, case in enumerate(selected, start=1):
        reporter.set_phase(f"Agent replay ({mode}) [{index}/{len(selected)}] {case.id}")

        if mode == "full_llm_shadow_replay" and total_calls >= total_limit:
            results.append(
                EvalCaseResult(
                    case_id=case.id,
                    name=case.name,
                    status="error",
                    failures=["max_total_reasoning_calls_exceeded"],
                )
            )
            reporter.advance(1)
            continue

        result = await run_eval_case(
            case,
            mode=mode,
            allow_real_llm=allow_real_llm,
            max_reasoning_calls=per_case_limit,
            settings_overrides=settings_overrides,
        )
        if mode == "full_llm_shadow_replay":
            trace = (result.full_shadow or {}).get("traceSummary") or {}
            total_calls += int(trace.get("totalReasoningCalls") or 0)
        results.append(result)
        reporter.advance(1)
    return results
