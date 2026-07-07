"""Full LLM shadow replay runner for eval lab (Phase 26)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

from app.agent.evaluation.fake_reasoning import FakeReasoningBlockRunner
from app.agent.evaluation.gates_eval import build_observed_from_case, evaluate_case_result
from app.agent.evaluation.llm_trace_summary import TracedReasoningBlockRunner, summarize_contract_calls
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseResult
from app.agent.evaluation.side_effect_firewall import EvalSideEffectFirewall, SideEffectViolation
from app.agent.schemas import AgentResponse, StructuredBlock
from app.config import Settings

logger = logging.getLogger(__name__)


def build_full_llm_shadow_lab_settings(*, base: Settings | None = None, overrides: dict[str, Any] | None = None) -> Settings:
    """Recommended lab settings for full LLM shadow replay."""
    payload: dict[str, Any] = {
        "AGENT_TASK_UNDERSTANDING_ENABLED": True,
        "AGENT_PLANNER_ENABLED": True,
        "AGENT_PLANNER_DRY_RUN": True,
        "AGENT_SUPERVISOR_ENABLED": True,
        "AGENT_SUPERVISOR_DRY_RUN": True,
        "AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED": True,
        "AGENT_DYNAMIC_AGENTS_ENABLED": True,
        "AGENT_DYNAMIC_AGENTS_DRY_RUN": True,
        "AGENT_PLANNER_DYNAMIC_SPECS_ENABLED": True,
        "AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN": True,
        "AGENT_MONITOR_ENABLED": True,
        "AGENT_MONITOR_DRY_RUN": True,
        "AGENT_CLARIFICATION_ENABLED": True,
        "AGENT_CLARIFICATION_USER_FACING_ENABLED": False,
        "AGENT_CLARIFICATION_STATE_ENABLED": False,
        "AGENT_PLAN_REPAIR_ENABLED": True,
        "AGENT_PLAN_REPAIR_DRY_RUN": True,
        "AGENT_PLAN_REPAIR_USE_LLM": True,
        "AGENT_SYNTHESIS_ENABLED": True,
        "AGENT_SYNTHESIS_DRY_RUN": True,
        "AGENT_SYNTHESIS_USE_LLM": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED": True,
        "AGENT_SYNTHESIS_TEXT_PROMOTION_MODE": "shadow_only",
        "AGENT_RUNTIME_READINESS_GATE_ENABLED": False,
        "AGENT_EVAL_SIDE_EFFECT_FIREWALL_ENABLED": True,
    }
    if overrides:
        payload.update(overrides)
    return Settings(**payload)


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


@asynccontextmanager
async def _reasoning_patch(*, case: EvalCase, allow_real_llm: bool, settings: Settings, max_calls: int):
    from app.agent.reasoning.reasoning_block import ReasoningBlock

    original_reasoning_run = ReasoningBlock.run

    if allow_real_llm and settings.is_agent_eval_full_llm_require_explicit_allow():
        inner: Any
        if case.mock_reasoning_outputs:
            inner = FakeReasoningBlockRunner(case.mock_reasoning_outputs)
        else:
            inner = ReasoningBlock(settings=settings)
        traced = TracedReasoningBlockRunner(inner)

        async def _limited_run(self: Any, input: Any) -> Any:
            if len(traced.summaries) >= max_calls:
                raise RuntimeError("max_reasoning_calls_exceeded")
            if case.mock_reasoning_outputs:
                return await traced.run(input)
            return await traced.run_via_original(self, input, original_reasoning_run)

        with patch("app.agent.reasoning.reasoning_block.ReasoningBlock.run", new=_limited_run):
            yield traced
    else:
        runner = TracedReasoningBlockRunner(FakeReasoningBlockRunner(case.mock_reasoning_outputs))

        async def _patched_run(_self: Any, input: Any) -> Any:
            return await runner.run(input)

        with patch("app.agent.reasoning.reasoning_block.ReasoningBlock.run", new=_patched_run):
            yield runner


async def _run_lab_pipeline(
    case: EvalCase,
    *,
    settings: Settings,
    allow_real_llm: bool,
    max_reasoning_calls: int,
) -> tuple[dict[str, Any], TracedReasoningBlockRunner]:
    replay_meta: dict[str, Any] = dict(case.retrieval_metadata)

    async with _reasoning_patch(case=case, allow_real_llm=allow_real_llm, settings=settings, max_calls=max_reasoning_calls) as traced:
        if settings.is_agent_task_understanding_enabled():
            from app.agent.task_understanding.integration import run_task_understanding_dry_run

            task_summary = await run_task_understanding_dry_run(
                user_message=case.user_message,
                deterministic_intent=str(case.compact_context.get("intent") or case.expected.expected_intent or ""),
                deterministic_intent_confidence=0.8,
                deterministic_entities=case.compact_context.get("entities") if isinstance(case.compact_context.get("entities"), dict) else {},
                settings=settings,
            )
            if task_summary:
                replay_meta["taskUnderstanding"] = task_summary

        if settings.is_agent_planner_enabled():
            from app.agent.planner.diagnostics import build_plan_with_diagnostics

            plan, planner_summary = await build_plan_with_diagnostics(
                user_message=case.user_message,
                task_understanding_summary=replay_meta.get("taskUnderstanding"),
                deterministic_intent=str(case.compact_context.get("intent") or case.expected.expected_intent or ""),
                deterministic_entities=case.compact_context.get("entities")
                if isinstance(case.compact_context.get("entities"), dict)
                else {},
                settings=settings,
            )
            if planner_summary:
                replay_meta["plannerDiagnostics"] = planner_summary

            if settings.is_agent_supervisor_enabled() and planner_summary and plan is not None:
                from app.agent.supervisor.diagnostics import run_supervisor_dry_run

                supervisor_summary = await run_supervisor_dry_run(
                    user_message=case.user_message,
                    planner_diagnostics=planner_summary,
                    planner_output=plan.model_dump(),
                    task_understanding_summary=replay_meta.get("taskUnderstanding"),
                    deterministic_intent=str(case.compact_context.get("intent") or case.expected.expected_intent or ""),
                    settings=settings,
                )
                if supervisor_summary:
                    replay_meta["supervisorDiagnostics"] = supervisor_summary

        synthesis_diag = replay_meta.get("synthesisDiagnostics") or {}
        from app.agent.clarification.guardrail_bridge import apply_clarification_guardrail

        replay_meta = apply_clarification_guardrail(
            user_message=case.user_message,
            replay_meta=replay_meta,
            enabled=settings.is_agent_clarification_enabled(),
        )

        if settings.is_agent_synthesis_enabled() and (synthesis_diag or case.expected.expected_synthesis_promotion != "not_applicable"):
            from app.agent.synthesis.promotion_diagnostics import build_synthesis_promotion_metadata
            from app.agent.synthesis.promotion_policy import evaluate_synthesis_text_promotion
            from app.agent.synthesis.schemas import SynthesisOutput

            synthesis_output = SynthesisOutput(
                status=synthesis_diag.get("status") or "skipped",  # type: ignore[arg-type]
                synthesis_id=f"eval-{case.id}",
                decision_summary="full shadow replay",
                candidate_answer_text=str(case.live_response_summary.get("textPreview") or "eval"),
                safe_to_show=bool(synthesis_diag.get("safeToShow", True)),
                safe_to_promote=False,
                confidence=float(synthesis_diag.get("confidence") or 0.0),
            )
            decision = evaluate_synthesis_text_promotion(
                workflow_name=str(case.compact_context.get("workflow") or case.expected.expected_workflow or ""),
                live_response=_build_live_response(case),
                synthesis_output=synthesis_output,
                retrieval_metadata=replay_meta,
                settings=settings,
            )
            replay_meta["synthesisPromotion"] = build_synthesis_promotion_metadata(decision)

    return replay_meta, traced


async def run_full_llm_shadow_eval_case(
    case: EvalCase,
    *,
    allow_real_llm: bool,
    max_reasoning_calls: int,
    settings_overrides: dict[str, Any] | None = None,
    firewall: EvalSideEffectFirewall | None = None,
) -> EvalCaseResult:
    """Run one case through the full LLM shadow lab pipeline."""
    if not allow_real_llm:
        return EvalCaseResult(
            case_id=case.id,
            name=case.name,
            status="error",
            failures=["full_llm_shadow_requires_allow_real_llm"],
        )

    settings = build_full_llm_shadow_lab_settings(overrides=settings_overrides)
    active_firewall = firewall or EvalSideEffectFirewall()
    owned_firewall = firewall is None
    if owned_firewall and settings.is_agent_eval_side_effect_firewall_enabled():
        active_firewall.install()

    try:
        replay_meta, traced = await _run_lab_pipeline(
            case,
            settings=settings,
            allow_real_llm=allow_real_llm,
            max_reasoning_calls=max_reasoning_calls,
        )
        trace_summary = summarize_contract_calls(traced.summaries)
        violations = active_firewall.violations()

        observed = build_observed_from_case(case, replay_observed=replay_meta)
        result = evaluate_case_result(case=case, observed=observed)

        if violations:
            result = result.model_copy(
                update={
                    "status": "failed",
                    "failures": [*result.failures, "side_effect_violation"],
                    "safety_failures": [*result.safety_failures, "side_effect_violation"],
                    "side_effect_violations": violations,
                }
            )

        promotion = replay_meta.get("synthesisPromotion") or {}
        would_promote = bool(promotion.get("wouldPromote") or promotion.get("promoted"))
        return result.model_copy(
            update={
                "reasoning_call_summaries": trace_summary.get("calls") or [],
                "side_effect_violations": violations,
                "full_shadow": {
                    "realLlmUsed": allow_real_llm,
                    "traceSummary": {
                        "totalReasoningCalls": trace_summary.get("totalReasoningCalls"),
                        "contractCallCounts": trace_summary.get("contractCallCounts"),
                        "schemaValidationFailures": trace_summary.get("schemaValidationFailures"),
                        "averageLatencyMs": trace_summary.get("averageLatencyMs"),
                        "totalEstimatedCostUsd": trace_summary.get("totalEstimatedCostUsd"),
                    },
                    "promotionWouldPromote": would_promote,
                    "casesRequiringClarification": 1
                    if observed.get("actual_clarification_action") in {"ask_user", "pending"}
                    else 0,
                },
            }
        )
    except SideEffectViolation:
        return EvalCaseResult(
            case_id=case.id,
            name=case.name,
            status="failed",
            failures=["side_effect_violation"],
            safety_failures=["side_effect_violation"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("full_llm_shadow_case_failed", extra={"caseId": case.id})
        return EvalCaseResult(
            case_id=case.id,
            name=case.name,
            status="error",
            failures=[f"full_shadow_error:{type(exc).__name__}"],
        )
    finally:
        if owned_firewall:
            active_firewall.uninstall()
