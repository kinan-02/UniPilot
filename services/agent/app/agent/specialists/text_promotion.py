"""Controlled Specialist Text Promotion gate (Phase 14).

`evaluate_specialist_text_promotion` is the single deterministic decision
point that decides whether one specialist's `answer_text` may replace
`AgentResponse.text` for the current turn — never the full response, never
its blocks/warnings/sources/proposed_actions. Mirrors
`supervisor.promotion.evaluate_promotion_decision` (Phase 9) closely:

- Hard-restricted to exactly one specialist (`graduation_progress_agent`)
  answering for exactly one workflow (`graduation_progress_workflow`),
  regardless of how `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS` is configured —
  see `_HARD_ALLOWED_TEXT_PROMOTION_AGENTS`/`_HARD_ALLOWED_TEXT_PROMOTION_WORKFLOWS`.
- Requires the existing Phase 11 specialist validation/comparison to have
  already passed cleanly for that specialist, a high-confidence, complete,
  action-free, tool-loop-budget-respecting specialist output, and a safe,
  non-empty `answer_text` (`answer_text_safety.check_answer_text_safety`).
- Defers unconditionally to Phase 9 workflow promotion: if a workflow
  candidate was already promoted for this turn, text promotion is blocked
  with `workflow_promotion_already_selected_response` before any other gate
  runs — two promotion systems never modify the same turn independently.
- Never raises: any unexpected input degrades to `status="failed"`, never to
  an exception escaping this module. Blocking is driven purely by whether
  `reasons` ends up non-empty (any severity) — exactly like
  `supervisor.promotion.evaluate_promotion_decision`, `severity` is
  classification metadata only, not a partial-credit threshold.
- Never calls an LLM, never touches the database, never performs a write or
  creates an action proposal.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.schemas import AgentResponse
from app.agent.specialists.answer_text_safety import check_answer_text_safety
from app.agent.specialists.text_promotion_schemas import (
    SpecialistTextPromotionDecision,
    SpecialistTextPromotionMode,
    SpecialistTextPromotionReason,
)
from app.agent.supervisor.validation_schemas import scan_for_forbidden_keys
from app.config import Settings

logger = logging.getLogger(__name__)

# Phase 14 hard ceilings: no configuration value can ever widen text-
# promotion eligibility past this single specialist/workflow pair.
# `AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS` may only *narrow* the agent set
# further (e.g. an empty value disables it entirely).
_HARD_ALLOWED_TEXT_PROMOTION_AGENTS: frozenset[str] = frozenset({"graduation_progress_agent"})
_HARD_ALLOWED_TEXT_PROMOTION_WORKFLOWS: frozenset[str] = frozenset({"graduation_progress_workflow"})

_MIN_CONFIDENCE = 0.85
_MAX_FORBIDDEN_KEYS_LISTED = 20


def eligible_text_promotion_agents(settings: Settings) -> frozenset[str]:
    """The actual, effective text-promotion-eligible specialist set for `settings`.

    Always a subset of `_HARD_ALLOWED_TEXT_PROMOTION_AGENTS`.
    """
    return _HARD_ALLOWED_TEXT_PROMOTION_AGENTS & settings.agent_specialist_text_promotion_configured_agents()


def eligible_text_promotion_workflows() -> frozenset[str]:
    """The hard-coded, non-configurable text-promotion-eligible workflow set.

    Unlike `eligible_text_promotion_agents`, there is no companion settings
    field narrowing this further — Phase 14 is scoped to exactly one
    workflow/specialist pair.
    """
    return _HARD_ALLOWED_TEXT_PROMOTION_WORKFLOWS


def _reason(code: str, severity: str = "warning", **details: Any) -> SpecialistTextPromotionReason:
    return SpecialistTextPromotionReason(code=code, severity=severity, details=details)


def _blocked(
    *, workflow_name: str | None, specialist_agent_name: str | None, mode: SpecialistTextPromotionMode,
    reasons: list[SpecialistTextPromotionReason],
) -> SpecialistTextPromotionDecision:
    return SpecialistTextPromotionDecision(
        status="blocked",
        promoted=False,
        mode=mode,
        workflow_name=workflow_name,
        specialist_agent_name=specialist_agent_name,
        reasons=reasons,
    )


def _as_dict(value: dict[str, Any] | None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def evaluate_specialist_text_promotion(
    *,
    workflow_name: str,
    specialist_agent_name: str | None,
    live_response_summary: dict[str, Any],
    specialist_validation_metadata: dict[str, Any] | None,
    specialist_comparison_metadata: dict[str, Any] | None,
    specialist_output_summary: dict[str, Any] | None,
    answer_text: str | None,
    workflow_promotion_already_promoted: bool,
    settings: Settings,
) -> SpecialistTextPromotionDecision:
    """Decide whether `answer_text` may replace `AgentResponse.text` for this turn.

    Every gate is documented inline. Never raises: any unexpected input
    (missing keys, wrong types, `None` where a dict was expected, ...)
    degrades to `status="failed"`.
    """
    try:
        enabled = settings.is_agent_specialist_text_promotion_enabled()
        mode = settings.agent_specialist_text_promotion_mode()

        if not enabled or mode == "off":
            return SpecialistTextPromotionDecision(
                status="skipped", promoted=False, mode="off", workflow_name=workflow_name,
                specialist_agent_name=specialist_agent_name,
            )

        if mode == "shadow_only":
            return SpecialistTextPromotionDecision(
                status="skipped", promoted=False, mode="shadow_only", workflow_name=workflow_name,
                specialist_agent_name=specialist_agent_name,
            )

        # From here on, mode == "promote_validated".

        # Phase 14 <-> Phase 9 precedence: two promotion systems must never
        # modify the same turn independently.
        if workflow_promotion_already_promoted:
            return _blocked(
                workflow_name=workflow_name,
                specialist_agent_name=specialist_agent_name,
                mode=mode,
                reasons=[_reason("workflow_promotion_already_selected_response", "info")],
            )

        eligibility_reasons: list[SpecialistTextPromotionReason] = []
        if workflow_name not in eligible_text_promotion_workflows():
            eligibility_reasons.append(
                _reason("workflow_not_eligible_for_text_promotion", "error", workflowName=workflow_name)
            )
        if specialist_agent_name not in eligible_text_promotion_agents(settings):
            eligibility_reasons.append(
                _reason(
                    "specialist_not_eligible_for_text_promotion", "error", specialistAgentName=specialist_agent_name
                )
            )
        if eligibility_reasons:
            return _blocked(
                workflow_name=workflow_name, specialist_agent_name=specialist_agent_name, mode=mode,
                reasons=eligibility_reasons,
            )

        if settings.is_agent_runtime_readiness_gate_enabled() and specialist_agent_name:
            from app.agent.readiness.diagnostics import build_runtime_readiness_diagnostic
            from app.agent.readiness.runtime_gate import (
                evaluate_runtime_gate_for_settings,
                specialist_text_promotion_candidate_id,
            )

            gate_decision = evaluate_runtime_gate_for_settings(
                candidate_id=specialist_text_promotion_candidate_id(specialist_agent_name),
                requested_scope=workflow_name,
                settings=settings,
            )
            runtime_diag = build_runtime_readiness_diagnostic(gate_decision, settings=settings)
            if not gate_decision.allowed:
                return SpecialistTextPromotionDecision(
                    status="blocked",
                    promoted=False,
                    mode=mode,
                    workflow_name=workflow_name,
                    specialist_agent_name=specialist_agent_name,
                    reasons=[_reason("runtime_readiness_gate_blocked", "error", reasons=gate_decision.reasons[:5])],
                    diagnostics={"runtimeReadiness": runtime_diag},
                )

        reasons: list[SpecialistTextPromotionReason] = []

        validation = _as_dict(specialist_validation_metadata)
        if specialist_validation_metadata is None:
            reasons.append(_reason("specialist_validation_missing", "error"))
        else:
            validation_status = validation.get("status")
            if validation_status != "passed":
                reasons.append(_reason("specialist_validation_not_passed", "error", status=validation_status))
            if not bool(validation.get("safeToConsider")):
                reasons.append(_reason("specialist_validation_not_safe_to_consider", "error"))

        comparison = _as_dict(specialist_comparison_metadata)
        if specialist_comparison_metadata is None:
            reasons.append(_reason("specialist_comparison_missing", "error"))
        else:
            if not bool(comparison.get("comparable")):
                reasons.append(_reason("specialist_comparison_not_comparable", "error"))
            if not bool(comparison.get("safeMatch")):
                reasons.append(_reason("specialist_comparison_not_safe_match", "error"))

        output_summary = _as_dict(specialist_output_summary)
        if specialist_output_summary is None:
            reasons.append(_reason("specialist_output_missing", "error"))
        else:
            output_status = output_summary.get("status")
            if output_status != "completed":
                reasons.append(_reason("specialist_output_not_completed", "error", status=output_status))

            try:
                confidence = float(output_summary.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence < _MIN_CONFIDENCE:
                reasons.append(_reason("specialist_confidence_too_low", "warning", confidence=confidence))

            if int(output_summary.get("missingContextCount") or 0) > 0:
                reasons.append(_reason("specialist_missing_context_present", "error"))

            if bool(output_summary.get("hasProposedActions")):
                reasons.append(_reason("specialist_has_proposed_actions", "error"))

            if output_summary.get("toolLoopStatus") == "budget_exceeded":
                reasons.append(_reason("specialist_tool_loop_budget_exceeded", "error"))

            if int(output_summary.get("rejectedObservationCount") or 0) > 0:
                reasons.append(
                    _reason(
                        "specialist_has_rejected_tool_requests",
                        "warning",
                        count=int(output_summary.get("rejectedObservationCount") or 0),
                    )
                )

        if not answer_text or not str(answer_text).strip():
            reasons.append(_reason("specialist_answer_text_missing_or_invalid", "error"))
        else:
            reasons.extend(
                check_answer_text_safety(
                    answer_text, max_chars=settings.resolved_agent_specialist_text_promotion_max_chars()
                )
            )

        live_summary = _as_dict(live_response_summary)
        live_proposed_count = int(
            live_summary.get("proposedActionCount") or live_summary.get("proposed_action_count") or 0
        )
        if live_proposed_count:
            reasons.append(_reason("live_response_has_proposed_actions", "error"))

        live_block_count = int(live_summary.get("blockCount") or 0)
        if live_block_count <= 0:
            reasons.append(_reason("live_response_has_no_blocks", "error"))

        forbidden_hits = scan_for_forbidden_keys(
            {
                "liveResponseSummary": live_response_summary,
                "specialistValidation": specialist_validation_metadata,
                "specialistComparison": specialist_comparison_metadata,
                "specialistOutput": specialist_output_summary,
            }
        )
        if forbidden_hits:
            reasons.append(
                _reason(
                    "forbidden_diagnostic_payload_detected",
                    "error",
                    keys=forbidden_hits[:_MAX_FORBIDDEN_KEYS_LISTED],
                )
            )

        if reasons:
            return _blocked(
                workflow_name=workflow_name, specialist_agent_name=specialist_agent_name, mode=mode, reasons=reasons
            )

        return SpecialistTextPromotionDecision(
            status="promoted",
            promoted=True,
            mode=mode,
            workflow_name=workflow_name,
            specialist_agent_name=specialist_agent_name,
        )
    except Exception:  # noqa: BLE001 — must never raise into a live turn
        logger.exception("specialist_text_promotion_evaluation_failed")
        return SpecialistTextPromotionDecision(
            status="failed",
            promoted=False,
            mode="promote_validated",
            workflow_name=workflow_name if isinstance(workflow_name, str) else None,
            specialist_agent_name=specialist_agent_name if isinstance(specialist_agent_name, str) else None,
            reasons=[_reason("text_promotion_evaluation_error", "error")],
        )


def build_text_promoted_response(*, live_response: AgentResponse, answer_text: str) -> AgentResponse:
    """Copy `live_response`, replacing only `text` with `answer_text`.

    Never mutates `live_response`. Never raises: a malformed `live_response`
    (not a real `AgentResponse`) or an unexpected copy failure degrades to
    returning `live_response` unchanged rather than raising — the caller
    (`supervisor.post_context_runner`) only ever calls this after every
    other promotion gate already passed, so this is defense in depth, not
    the primary safety boundary.
    """
    try:
        if not isinstance(live_response, AgentResponse):
            return live_response
        return live_response.model_copy(update={"text": str(answer_text)})
    except Exception:  # noqa: BLE001 — must never raise into a live turn
        logger.exception("specialist_text_promoted_response_build_failed")
        return live_response


__all__ = [
    "build_text_promoted_response",
    "eligible_text_promotion_agents",
    "eligible_text_promotion_workflows",
    "evaluate_specialist_text_promotion",
]
