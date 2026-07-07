"""Report-only promotion readiness audit (Phase 28.2)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.agent.readiness.manifest_loader import find_manifest_candidate, load_runtime_readiness_manifest
from app.agent.readiness.runtime_gate import (
    evaluate_runtime_readiness_gate,
    synthesis_text_promotion_candidate_id,
)
from app.agent.readiness.schemas import RuntimeReadinessGateInput, RuntimeReadinessManifest
from app.agent.synthesis.promotion_policy import eligible_synthesis_text_promotion_workflows
from app.config import Settings


def _utc_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _manifest_stale(manifest: RuntimeReadinessManifest, *, max_age_days: int, now: datetime) -> bool:
    reference = manifest.reviewed_at or manifest.generated_at
    if reference is None:
        return True
    return _utc_now(now) - _utc_now(reference) > timedelta(days=max(1, max_age_days))


def audit_promotion_readiness(
    *,
    workflow_name: str,
    candidate_id: str,
    settings: Settings,
    manifest_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Answer whether promotion would be allowed right now. Report-only."""
    current = _utc_now(now)
    block_reasons: list[str] = []
    hard_ceiling = eligible_synthesis_text_promotion_workflows(settings)
    hard_ceiling_passed = workflow_name in hard_ceiling

    manifest_exists = False
    manifest_stale = False
    candidate_found = False
    candidate_approved = False
    candidate_expired = False
    scope_match = False
    readiness_level: str | None = None
    human_reviewed = False
    gate_decision_allowed = False
    gate_reasons: list[str] = []

    resolved_manifest_path = str(manifest_path or settings.resolved_agent_runtime_readiness_manifest_path() or "")
    manifest = load_runtime_readiness_manifest(resolved_manifest_path) if resolved_manifest_path else None
    manifest_exists = manifest is not None

    if manifest is not None:
        manifest_stale = _manifest_stale(
            manifest,
            max_age_days=settings.resolved_agent_runtime_readiness_max_age_days(),
            now=current,
        )
        human_reviewed = bool(manifest.reviewed_at and manifest.reviewed_by)
        candidate = find_manifest_candidate(manifest, candidate_id)
        candidate_found = candidate is not None
        if candidate is not None:
            candidate_approved = bool(candidate.approved)
            readiness_level = candidate.level
            scope_match = workflow_name in set(candidate.scope)
            if candidate.expires_at is not None and current >= _utc_now(candidate.expires_at):
                candidate_expired = True

    if not hard_ceiling_passed:
        block_reasons.append("workflow_not_in_hard_ceiling")

    if settings.is_agent_runtime_readiness_gate_enabled():
        if not manifest_exists:
            block_reasons.append("manifest_missing")
        elif manifest is not None:
            if manifest_stale:
                block_reasons.append("manifest_stale")
            if settings.is_agent_runtime_readiness_require_human_review() and not human_reviewed:
                block_reasons.append("human_review_missing")
            if not candidate_found:
                block_reasons.append("candidate_not_found")
            elif not candidate_approved:
                block_reasons.append("candidate_not_approved")
            if candidate_expired:
                block_reasons.append("candidate_expired")
            if candidate_found and not scope_match:
                block_reasons.append("scope_mismatch")

            gate_input = RuntimeReadinessGateInput(
                candidate_id=candidate_id,
                requested_scope=workflow_name,
                required_level=settings.agent_runtime_readiness_min_level(),  # type: ignore[arg-type]
                require_human_review=settings.is_agent_runtime_readiness_require_human_review(),
            )
            gate_decision = evaluate_runtime_readiness_gate(
                gate_input=gate_input,
                manifest=manifest,
                settings=settings,
                now=current,
            )
            gate_decision_allowed = gate_decision.allowed
            gate_reasons = list(gate_decision.reasons)
            if not gate_decision_allowed:
                block_reasons.extend(gate_reasons)

    normal_promotion_gate_required = True
    if not settings.is_agent_synthesis_text_promotion_enabled():
        block_reasons.append("synthesis_text_promotion_disabled")
    if settings.agent_synthesis_text_promotion_mode() == "off":
        block_reasons.append("synthesis_text_promotion_mode_off")
    if settings.agent_synthesis_text_promotion_mode() != "promote_validated":
        block_reasons.append("synthesis_text_promotion_mode_not_promote_validated")

    if candidate_id != synthesis_text_promotion_candidate_id(workflow_name):
        block_reasons.append("candidate_id_workflow_mismatch")

    would_allow = not block_reasons
    return {
        "workflowName": workflow_name,
        "candidateId": candidate_id,
        "finalDecision": "would_allow" if would_allow else "would_block",
        "blockReasons": sorted(set(block_reasons)),
        "configFlags": {
            "runtimeReadinessGateEnabled": settings.is_agent_runtime_readiness_gate_enabled(),
            "runtimeReadinessFailClosed": settings.is_agent_runtime_readiness_fail_closed(),
            "runtimeReadinessRequireHumanReview": settings.is_agent_runtime_readiness_require_human_review(),
            "runtimeReadinessMinLevel": settings.agent_runtime_readiness_min_level(),
            "synthesisTextPromotionEnabled": settings.is_agent_synthesis_text_promotion_enabled(),
            "synthesisTextPromotionMode": settings.agent_synthesis_text_promotion_mode(),
            "supervisorPromotionEnabled": settings.is_agent_supervisor_promotion_enabled(),
            "supervisorPromotionMode": settings.agent_supervisor_promotion_mode(),
        },
        "hardWorkflowCeilingPassed": hard_ceiling_passed,
        "hardWorkflowCeiling": sorted(hard_ceiling),
        "manifestPath": resolved_manifest_path or None,
        "manifestExists": manifest_exists,
        "manifestStale": manifest_stale,
        "candidateApprovalExists": candidate_found,
        "candidateApproved": candidate_approved,
        "candidateExpired": candidate_expired,
        "scopeMatch": scope_match,
        "readinessLevel": readiness_level,
        "humanReviewed": human_reviewed,
        "runtimeGateAllowed": gate_decision_allowed,
        "runtimeGateReasons": gate_reasons,
        "normalPromotionGateStillRequired": normal_promotion_gate_required,
        "reportOnly": True,
    }
