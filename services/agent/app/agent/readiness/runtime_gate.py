"""Runtime readiness gate evaluation (Phase 25)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.agent.readiness.manifest_loader import find_manifest_candidate
from app.agent.readiness.schemas import (
    RuntimeReadinessGateDecision,
    RuntimeReadinessGateInput,
    RuntimeReadinessLevel,
    RuntimeReadinessManifest,
    level_at_least,
)
from app.config import Settings


def synthesis_text_promotion_candidate_id(workflow_name: str) -> str:
    return f"synthesis_text_promotion.{workflow_name}"


def specialist_text_promotion_candidate_id(specialist_agent_name: str) -> str:
    return f"specialist_text_promotion.{specialist_agent_name}"


def workflow_promotion_candidate_id(workflow_name: str) -> str:
    return f"workflow_promotion.{workflow_name}"


def _utc_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _manifest_reference_time(manifest: RuntimeReadinessManifest) -> datetime | None:
    return manifest.reviewed_at or manifest.generated_at


def evaluate_runtime_readiness_gate(
    *,
    gate_input: RuntimeReadinessGateInput,
    manifest: RuntimeReadinessManifest | None,
    settings: Settings,
    now: datetime | None = None,
) -> RuntimeReadinessGateDecision:
    """Evaluate whether a promotion candidate is approved in the activation manifest."""
    current = _utc_now(now)

    if not settings.is_agent_runtime_readiness_gate_enabled():
        return RuntimeReadinessGateDecision(
            allowed=True,
            candidate_id=gate_input.candidate_id,
            reasons=["gate_disabled"],
            reviewed=False,
            scope_allowed=True,
        )

    if manifest is None:
        if settings.is_agent_runtime_readiness_fail_closed():
            return RuntimeReadinessGateDecision(
                allowed=False,
                candidate_id=gate_input.candidate_id,
                reasons=["manifest_missing"],
            )
        return RuntimeReadinessGateDecision(
            allowed=True,
            candidate_id=gate_input.candidate_id,
            reasons=["manifest_missing_fail_open"],
            reviewed=False,
            scope_allowed=True,
        )

    reference_time = _manifest_reference_time(manifest)
    stale = False
    if reference_time is not None:
        max_age = timedelta(days=settings.resolved_agent_runtime_readiness_max_age_days())
        if current - _utc_now(reference_time) > max_age:
            stale = True

    reviewed = bool(manifest.reviewed_at and manifest.reviewed_by)
    if gate_input.require_human_review and settings.is_agent_runtime_readiness_require_human_review():
        if not reviewed:
            return RuntimeReadinessGateDecision(
                allowed=False,
                candidate_id=gate_input.candidate_id,
                reasons=["human_review_missing"],
                reviewed=False,
                stale=stale,
            )

    if stale:
        return RuntimeReadinessGateDecision(
            allowed=False,
            candidate_id=gate_input.candidate_id,
            reasons=["manifest_stale"],
            reviewed=reviewed,
            stale=True,
        )

    candidate = find_manifest_candidate(manifest, gate_input.candidate_id)
    if candidate is None:
        return RuntimeReadinessGateDecision(
            allowed=False,
            candidate_id=gate_input.candidate_id,
            reasons=["candidate_not_found"],
            reviewed=reviewed,
            stale=False,
        )

    if not candidate.approved:
        return RuntimeReadinessGateDecision(
            allowed=False,
            candidate_id=gate_input.candidate_id,
            level=candidate.level,
            reasons=["candidate_not_approved"],
            reviewed=reviewed,
            stale=False,
        )

    if candidate.expires_at is not None and current >= _utc_now(candidate.expires_at):
        return RuntimeReadinessGateDecision(
            allowed=False,
            candidate_id=gate_input.candidate_id,
            level=candidate.level,
            reasons=["candidate_expired"],
            reviewed=reviewed,
            stale=False,
        )

    required_level: RuntimeReadinessLevel = gate_input.required_level
    if not level_at_least(candidate.level, required_level):
        return RuntimeReadinessGateDecision(
            allowed=False,
            candidate_id=gate_input.candidate_id,
            level=candidate.level,
            reasons=["level_below_required"],
            reviewed=reviewed,
            stale=False,
        )

    scope_allowed = True
    if gate_input.requested_scope:
        scope_allowed = gate_input.requested_scope in set(candidate.scope)
        if not scope_allowed:
            return RuntimeReadinessGateDecision(
                allowed=False,
                candidate_id=gate_input.candidate_id,
                level=candidate.level,
                reasons=["scope_mismatch"],
                reviewed=reviewed,
                stale=False,
                scope_allowed=False,
            )

    return RuntimeReadinessGateDecision(
        allowed=True,
        candidate_id=gate_input.candidate_id,
        level=candidate.level,
        reasons=["approved"],
        reviewed=reviewed,
        stale=False,
        scope_allowed=scope_allowed,
    )


def load_manifest_for_settings(settings: Settings):
    from app.agent.readiness.manifest_loader import load_runtime_readiness_manifest

    path = settings.resolved_agent_runtime_readiness_manifest_path()
    if not path:
        return None
    return load_runtime_readiness_manifest(path)


def evaluate_runtime_gate_for_settings(
    *,
    candidate_id: str,
    requested_scope: str | None,
    settings: Settings,
    manifest: RuntimeReadinessManifest | None = None,
    now: datetime | None = None,
) -> RuntimeReadinessGateDecision:
    gate_input = RuntimeReadinessGateInput(
        candidate_id=candidate_id,
        requested_scope=requested_scope,
        required_level=settings.agent_runtime_readiness_min_level(),  # type: ignore[arg-type]
        require_human_review=settings.is_agent_runtime_readiness_require_human_review(),
    )
    resolved_manifest = manifest
    if resolved_manifest is None and settings.is_agent_runtime_readiness_gate_enabled():
        resolved_manifest = load_manifest_for_settings(settings)
    return evaluate_runtime_readiness_gate(
        gate_input=gate_input,
        manifest=resolved_manifest,
        settings=settings,
        now=now,
    )
