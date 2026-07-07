"""Controlled synthesis text promotion policy (Phase 22)."""

from __future__ import annotations

import logging
from typing import Any

from app.agent.schemas import AgentResponse
from app.agent.synthesis.candidate_safety import check_synthesis_candidate_safety
from app.agent.synthesis.live_compare import compare_synthesis_candidate_to_live_response
from app.agent.synthesis.promotion_schemas import (
    SynthesisTextPromotionDecision,
    SynthesisTextPromotionMode,
    SynthesisTextPromotionReason,
)
from app.agent.synthesis.schemas import SynthesisInput, SynthesisOutput
from app.agent.synthesis.trust_policy import monitor_blocks_promotion, unresolved_high_severity_conflicts
from app.config import Settings

logger = logging.getLogger(__name__)

_HARD_ALLOWED_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS: frozenset[str] = frozenset(
    {
        "graduation_progress_workflow",
        "course_question_workflow",
        "requirement_explanation_workflow",
    }
)

_HARD_EXCLUDED_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS: frozenset[str] = frozenset(
    {
        "transcript_import_workflow",
        "semester_planning_workflow",
        "profile_update_workflow",
    }
)


def eligible_synthesis_text_promotion_workflows(settings: Settings) -> frozenset[str]:
    configured = settings.synthesis_text_promotion_configured_workflows()
    return _HARD_ALLOWED_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS & configured - _HARD_EXCLUDED_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS


def _reason(code: str, severity: str = "warning", **details: Any) -> SynthesisTextPromotionReason:
    return SynthesisTextPromotionReason(code=code, severity=severity, details=details)


def _blocked(
    *,
    workflow_name: str | None,
    mode: SynthesisTextPromotionMode,
    reasons: list[SynthesisTextPromotionReason],
    synthesis_output: SynthesisOutput | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> SynthesisTextPromotionDecision:
    confidence = synthesis_output.confidence if synthesis_output is not None else 0.0
    candidate_chars = len((synthesis_output.candidate_answer_text or "") if synthesis_output else "")
    return SynthesisTextPromotionDecision(
        status="blocked",
        promoted=False,
        mode=mode,
        workflow_name=workflow_name,
        synthesis_status=synthesis_output.status if synthesis_output else None,
        reasons=reasons,
        candidate_char_count=candidate_chars,
        confidence=confidence,
        diagnostics=diagnostics or {},
    )


def _skipped(
    *,
    workflow_name: str | None,
    mode: SynthesisTextPromotionMode,
    reasons: list[SynthesisTextPromotionReason],
    diagnostics: dict[str, Any] | None = None,
) -> SynthesisTextPromotionDecision:
    return SynthesisTextPromotionDecision(
        status="skipped",
        promoted=False,
        mode=mode,
        workflow_name=workflow_name,
        reasons=reasons,
        diagnostics=diagnostics or {},
    )


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def synthesis_output_promotion_ready(
    output: SynthesisOutput,
    *,
    settings: Settings,
    monitor_summary: dict[str, Any] | None = None,
    plan_repair_summary: dict[str, Any] | None = None,
) -> bool:
    """Deterministic synthesis-side readiness — does not inspect live response."""
    if output.status not in {"candidate_ready", "candidate_ready_with_warnings"}:
        return False
    if not output.safe_to_show:
        return False
    if output.confidence < float(settings.agent_synthesis_text_promotion_min_confidence):
        return False
    if not (output.candidate_answer_text or "").strip():
        return False
    if unresolved_high_severity_conflicts(output.conflicts):
        return False
    monitor = _as_dict(monitor_summary)
    if monitor_blocks_promotion(monitor):
        return False
    repair = _as_dict(plan_repair_summary)
    if str(repair.get("modeUsed") or "") in {"regenerate", "abort_safely"}:
        return False
    return True


def _clarification_blocks_promotion(retrieval_metadata: dict[str, Any]) -> bool:
    state = _as_dict(retrieval_metadata.get("clarificationState"))
    if str(state.get("status") or "") != "pending":
        return False
    clar = _as_dict(retrieval_metadata.get("clarificationDiagnostics"))
    for question in clar.get("questions") or []:
        if not isinstance(question, dict):
            continue
        if question.get("ambiguityType") == "preference" and question.get("consequence") in {"high", "medium"}:
            return True
    return False


def evaluate_synthesis_text_promotion(
    *,
    workflow_name: str | None,
    live_response: AgentResponse | None,
    synthesis_output: SynthesisOutput | None,
    retrieval_metadata: dict[str, Any],
    settings: Settings,
    existing_promotion_already_applied: bool = False,
    workflow_promotion_already_applied: bool = False,
    specialist_text_promotion_already_applied: bool = False,
) -> SynthesisTextPromotionDecision:
    """Decide whether synthesis candidate text may replace `AgentResponse.text`. Never raises."""
    try:
        enabled = settings.is_agent_synthesis_text_promotion_enabled()
        mode = settings.agent_synthesis_text_promotion_mode()  # type: ignore[assignment]
        runtime_readiness_diag: dict[str, Any] | None = None

        if not enabled or mode == "off":
            return _skipped(
                workflow_name=workflow_name,
                mode="off",
                reasons=[_reason("text_promotion_disabled", "info")],
            )

        if workflow_promotion_already_applied:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("existing_workflow_promotion_applied", "error")],
                synthesis_output=synthesis_output,
            )

        if specialist_text_promotion_already_applied:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("existing_specialist_text_promotion_applied", "error")],
                synthesis_output=synthesis_output,
            )

        if existing_promotion_already_applied:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("existing_promotion_applied", "error")],
                synthesis_output=synthesis_output,
            )

        wf = (workflow_name or "").strip()
        if not wf or wf not in eligible_synthesis_text_promotion_workflows(settings):
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("workflow_not_eligible_for_text_promotion", "error", workflowName=wf)],
                synthesis_output=synthesis_output,
            )

        if wf in _HARD_EXCLUDED_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("workflow_not_read_only", "error", workflowName=wf)],
                synthesis_output=synthesis_output,
            )

        if settings.is_agent_runtime_readiness_gate_enabled():
            from app.agent.readiness.diagnostics import build_runtime_readiness_diagnostic
            from app.agent.readiness.runtime_gate import (
                evaluate_runtime_gate_for_settings,
                synthesis_text_promotion_candidate_id,
            )

            gate_decision = evaluate_runtime_gate_for_settings(
                candidate_id=synthesis_text_promotion_candidate_id(wf),
                requested_scope=wf,
                settings=settings,
            )
            runtime_readiness_diag = build_runtime_readiness_diagnostic(gate_decision, settings=settings)
            if not gate_decision.allowed:
                return _blocked(
                    workflow_name=workflow_name,
                    mode=mode,
                    reasons=[_reason("runtime_readiness_gate_blocked", "error", reasons=gate_decision.reasons[:5])],
                    synthesis_output=synthesis_output,
                    diagnostics={"runtimeReadiness": runtime_readiness_diag},
                )

        if live_response is None or not isinstance(live_response, AgentResponse):
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("live_response_missing", "error")],
                synthesis_output=synthesis_output,
            )

        if live_response.proposed_actions:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("live_response_has_proposed_actions", "error")],
                synthesis_output=synthesis_output,
            )

        if settings.is_agent_synthesis_text_promotion_require_blocks() and not live_response.blocks:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("live_response_missing_blocks", "error")],
                synthesis_output=synthesis_output,
            )

        if synthesis_output is None:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("synthesis_output_missing", "error")],
            )

        monitor_summary = _as_dict(retrieval_metadata.get("monitorDiagnostics"))
        plan_repair_summary = _as_dict(retrieval_metadata.get("planRepairDiagnostics"))

        if synthesis_output.status in {"unsafe", "failed", "skipped", "insufficient_evidence"}:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("synthesis_status_not_promotable", "error", status=synthesis_output.status)],
                synthesis_output=synthesis_output,
            )

        candidate_text = (synthesis_output.candidate_answer_text or "").strip()
        if not candidate_text:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("synthesis_candidate_text_missing", "error")],
                synthesis_output=synthesis_output,
            )

        reasons: list[SynthesisTextPromotionReason] = []

        if not synthesis_output.safe_to_show:
            reasons.append(_reason("synthesis_not_safe_to_show", "error"))

        if not synthesis_output_promotion_ready(
            synthesis_output,
            settings=settings,
            monitor_summary=monitor_summary,
            plan_repair_summary=plan_repair_summary,
        ):
            reasons.append(_reason("synthesis_not_promotion_ready", "error"))

        if unresolved_high_severity_conflicts(synthesis_output.conflicts):
            reasons.append(_reason("unresolved_conflict", "error"))

        if monitor_blocks_promotion(monitor_summary):
            reasons.append(_reason("monitor_unsafe_output", "error"))

        decision = _as_dict(monitor_summary.get("decision"))
        if str(decision.get("action") or "") == "abort_safely":
            reasons.append(_reason("monitor_abort_safely", "error"))

        if str(plan_repair_summary.get("modeUsed") or "") in {"regenerate", "abort_safely"}:
            reasons.append(_reason("plan_repair_not_promotable", "error"))

        if _clarification_blocks_promotion(retrieval_metadata):
            reasons.append(_reason("clarification_pending", "error"))

        safety_reasons = check_synthesis_candidate_safety(
            candidate_text,
            max_chars=settings.resolved_agent_synthesis_text_promotion_max_chars(),
            uncertainty_notes=synthesis_output.uncertainty_notes,
        )
        for safety in safety_reasons:
            reasons.append(_reason(safety.code, safety.severity))

        compare_diag = compare_synthesis_candidate_to_live_response(
            candidate_text=candidate_text,
            live_response=live_response,
            synthesis_output=synthesis_output,
        )

        would_promote = not reasons
        diagnostics: dict[str, Any] = {"wouldPromote": would_promote, "comparison": compare_diag}
        if runtime_readiness_diag is not None:
            diagnostics["runtimeReadiness"] = runtime_readiness_diag

        if reasons:
            return _blocked(
                workflow_name=workflow_name,
                mode=mode,
                reasons=reasons,
                synthesis_output=synthesis_output,
                diagnostics=diagnostics,
            )

        if mode == "shadow_only":
            return _skipped(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("shadow_only", "info")],
                diagnostics={**diagnostics, "wouldPromote": True},
            )

        if mode != "promote_validated":
            return _skipped(
                workflow_name=workflow_name,
                mode=mode,
                reasons=[_reason("unsupported_mode", "warning", mode=mode)],
                diagnostics=diagnostics,
            )

        promoted_diagnostics = dict(diagnostics)
        return SynthesisTextPromotionDecision(
            status="promoted",
            promoted=True,
            mode=mode,
            workflow_name=workflow_name,
            synthesis_status=synthesis_output.status,
            candidate_char_count=len(candidate_text),
            confidence=synthesis_output.confidence,
            diagnostics=promoted_diagnostics,
        )
    except Exception:  # noqa: BLE001
        logger.exception("synthesis_text_promotion_evaluation_failed")
        return SynthesisTextPromotionDecision(
            status="failed",
            promoted=False,
            mode="promote_validated",
            workflow_name=workflow_name if isinstance(workflow_name, str) else None,
            reasons=[_reason("text_promotion_evaluation_error", "error")],
        )


__all__ = [
    "eligible_synthesis_text_promotion_workflows",
    "evaluate_synthesis_text_promotion",
    "synthesis_output_promotion_ready",
]
