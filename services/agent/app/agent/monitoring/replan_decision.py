"""Deterministic replan/repair decision policy (Phase 16)."""

from __future__ import annotations

from app.agent.monitoring.schemas import DivergenceKind, DivergenceSignal, MonitorInput, ReplanDecision


def decide_replan_action(signals: list[DivergenceSignal], input: MonitorInput) -> ReplanDecision:
    """Apply the Phase 16 priority order and return one diagnostic decision."""
    non_none = [signal for signal in signals if signal.kind != "none"]
    if not non_none:
        return ReplanDecision(
            action="continue",
            reason="no_divergence_detected",
            confidence=0.9,
            divergence_kinds=["none"],
            repair_scope="none",
        )

    kinds = [signal.kind for signal in non_none]
    affected_subtasks = sorted({sid for signal in non_none for sid in signal.related_subtask_ids})
    affected_assumptions = sorted({aid for signal in non_none for aid in signal.related_assumption_ids})

    if _has_kind(non_none, "unsafe_output"):
        return ReplanDecision(
            action="abort_safely",
            reason="unsafe_output_detected",
            confidence=0.95,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            affected_assumptions=affected_assumptions,
            repair_scope="entire_plan",
        )

    if _has_kind(non_none, "goal_drift"):
        return ReplanDecision(
            action="request_plan_regeneration",
            reason="goal_drift_detected",
            confidence=0.85,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            affected_assumptions=affected_assumptions,
            repair_scope="entire_plan",
        )

    if _has_kind(non_none, "assumption_violation"):
        return ReplanDecision(
            action="request_plan_repair",
            reason="assumption_violation_detected",
            confidence=0.8,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            affected_assumptions=affected_assumptions,
            repair_scope=_repair_scope_for_subtasks(input, affected_subtasks),
        )

    if _has_kind(non_none, "exhausted_path"):
        return ReplanDecision(
            action="request_plan_repair",
            reason="exhausted_path_detected",
            confidence=0.75,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            repair_scope="remaining_plan",
        )

    missing_signals = [signal for signal in non_none if signal.kind == "missing_context"]
    if missing_signals:
        if _any_preference_ambiguity(missing_signals):
            return ReplanDecision(
                action="ask_clarification",
                reason="missing_preference_context",
                confidence=0.7,
                divergence_kinds=kinds,
                affected_subtasks=affected_subtasks,
                clarification_needed=True,
                repair_scope="current_step",
            )
        return ReplanDecision(
            action="request_plan_repair",
            reason="missing_epistemic_context",
            confidence=0.72,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            repair_scope="remaining_plan",
        )

    if _has_kind(non_none, "local_execution_failure"):
        action = "local_substitute" if len(affected_subtasks) > 1 else "local_retry"
        return ReplanDecision(
            action=action,
            reason="local_execution_failure_detected",
            confidence=0.65,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            repair_scope="current_step",
        )

    if _has_kind(non_none, "budget_exceeded"):
        return ReplanDecision(
            action="request_plan_repair",
            reason="supervisor_budget_exceeded",
            confidence=0.7,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            repair_scope="remaining_plan",
        )

    if _has_kind(non_none, "validation_failure"):
        return ReplanDecision(
            action="request_plan_repair",
            reason="validation_failure_detected",
            confidence=0.68,
            divergence_kinds=kinds,
            affected_subtasks=affected_subtasks,
            repair_scope="remaining_plan",
        )

    if _has_kind(non_none, "promotion_blocked"):
        return ReplanDecision(
            action="continue",
            reason="promotion_blocked_informational",
            confidence=0.6,
            divergence_kinds=kinds,
            repair_scope="none",
        )

    return ReplanDecision(
        action="continue",
        reason="non_critical_warnings_only",
        confidence=0.55,
        divergence_kinds=kinds,
        affected_subtasks=affected_subtasks,
        repair_scope="none",
    )


def _has_kind(signals: list[DivergenceSignal], kind: DivergenceKind) -> bool:
    return any(signal.kind == kind for signal in signals)


def _any_preference_ambiguity(signals: list[DivergenceSignal]) -> bool:
    return any(isinstance(signal.evidence, dict) and signal.evidence.get("preferenceAmbiguity") for signal in signals)


def _repair_scope_for_subtasks(input: MonitorInput, affected_subtasks: list[str]) -> str:
    if input.current_step_id and input.current_step_id in affected_subtasks:
        return "current_step"
    if affected_subtasks:
        return "remaining_plan"
    return "entire_plan"
