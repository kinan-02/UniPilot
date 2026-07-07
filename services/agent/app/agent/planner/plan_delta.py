"""Deterministic plan execution delta builders (Phase 19)."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.planner.repair_schemas import PlanDeltaKind, PlanExecutionDelta

_MONITOR_KIND_MAP: dict[str, PlanDeltaKind] = {
    "goal_drift": "goal_drift",
    "assumption_violation": "assumption_violated",
    "missing_context": "missing_context_unresolved",
    "unsafe_output": "unsafe_output_detected",
    "local_execution_failure": "subtask_failed",
    "exhausted_path": "exhausted_path",
    "validation_failure": "validation_failed",
    "budget_exceeded": "budget_exceeded",
}


def _new_delta_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def delta_from_clarification_resolution(
    *,
    clarification_state_metadata: dict[str, Any],
    confirmed_answers: list[dict[str, Any]],
    assumptions_created: list[dict[str, Any]] | None = None,
) -> PlanExecutionDelta | None:
    """Build a clarification-answered delta. Never raises."""
    try:
        if not confirmed_answers:
            return None

        status = str(clarification_state_metadata.get("status") or "")
        if status not in {"confirmed", "assumed"}:
            return None

        return PlanExecutionDelta(
            delta_id=_new_delta_id("clarification"),
            source="clarification",
            kind="clarification_answered",
            summary="User clarification was resolved and can inform plan repair.",
            confirmed_answers=list(confirmed_answers),
            assumptions_created=list(assumptions_created or []),
            evidence={
                "clarificationId": clarification_state_metadata.get("clarificationId"),
                "answerCount": len(confirmed_answers),
            },
            consequence="medium",
        )
    except Exception:  # noqa: BLE001
        return None


def _signal_kind(signal: dict[str, Any]) -> str:
    return str(signal.get("kind") or signal.get("signalKind") or "").strip()


def _severity_to_consequence(severity: Any) -> str:
    value = str(severity or "medium").lower()
    if value in {"low", "medium", "high"}:
        return value
    if value in {"info", "warning"}:
        return "medium"
    if value == "error":
        return "high"
    return "medium"


def _map_monitor_signal(signal: dict[str, Any]) -> PlanExecutionDelta | None:
    kind_raw = _signal_kind(signal)
    mapped = _MONITOR_KIND_MAP.get(kind_raw)
    if mapped is None:
        return None

    related_subtasks = signal.get("relatedSubtaskIds") or signal.get("related_subtask_ids") or []
    related_assumptions = signal.get("relatedAssumptionIds") or signal.get("related_assumption_ids") or []
    if not isinstance(related_subtasks, list):
        related_subtasks = []
    if not isinstance(related_assumptions, list):
        related_assumptions = []

    evidence: dict[str, Any] = {"signalKind": kind_raw}
    ambiguity_type = signal.get("ambiguityType") or signal.get("ambiguity_type")
    if ambiguity_type:
        evidence["ambiguityType"] = ambiguity_type

    return PlanExecutionDelta(
        delta_id=_new_delta_id("monitor"),
        source="monitor",
        kind=mapped,
        summary=str(signal.get("summary") or signal.get("reason") or f"Monitor signal: {kind_raw}")[:240],
        affected_subtask_ids=[str(item) for item in related_subtasks if str(item).strip()],
        affected_assumption_ids=[str(item) for item in related_assumptions if str(item).strip()],
        monitor_signals=[{"kind": kind_raw, "severity": signal.get("severity")}],
        evidence=evidence,
        consequence=_severity_to_consequence(signal.get("severity") or signal.get("consequence")),  # type: ignore[arg-type]
    )


def deltas_from_monitor_diagnostics(monitor_diagnostics: dict[str, Any]) -> list[PlanExecutionDelta]:
    """Build deltas from compact monitor diagnostics. Never raises."""
    try:
        if not isinstance(monitor_diagnostics, dict) or not monitor_diagnostics:
            return []

        deltas: list[PlanExecutionDelta] = []
        signals = monitor_diagnostics.get("signals") or []
        if isinstance(signals, list):
            for signal in signals:
                if not isinstance(signal, dict):
                    continue
                delta = _map_monitor_signal(signal)
                if delta is not None:
                    deltas.append(delta)

        decision = monitor_diagnostics.get("decision") or {}
        if isinstance(decision, dict):
            action = str(decision.get("action") or "")
            reason = str(decision.get("reason") or "")
            if action == "request_plan_regeneration" and not any(d.kind == "goal_drift" for d in deltas):
                deltas.append(
                    PlanExecutionDelta(
                        delta_id=_new_delta_id("monitor-decision"),
                        source="monitor",
                        kind="goal_drift",
                        summary=reason[:240] or "Monitor requested plan regeneration.",
                        evidence={"decisionAction": action},
                        consequence="high",
                    )
                )
            elif action == "abort_safely" and not any(d.kind == "unsafe_output_detected" for d in deltas):
                deltas.append(
                    PlanExecutionDelta(
                        delta_id=_new_delta_id("monitor-decision"),
                        source="monitor",
                        kind="unsafe_output_detected",
                        summary=reason[:240] or "Monitor requested safe abort.",
                        evidence={"decisionAction": action},
                        consequence="high",
                    )
                )
            elif action == "ask_clarification" and not any(
                d.kind == "missing_context_unresolved" for d in deltas
            ):
                deltas.append(
                    PlanExecutionDelta(
                        delta_id=_new_delta_id("monitor-decision"),
                        source="monitor",
                        kind="missing_context_unresolved",
                        summary=reason[:240] or "Monitor requested clarification.",
                        evidence={
                            "decisionAction": action,
                            "ambiguityType": "preference",
                        },
                        consequence="medium",
                    )
                )
            elif action == "request_plan_repair" and not deltas:
                repair_kind: PlanDeltaKind = "subtask_failed"
                if any(_signal_kind(signal) == "exhausted_path" for signal in (signals if isinstance(signals, list) else [])):
                    repair_kind = "exhausted_path"
                elif reason and "exhausted_path" in reason:
                    repair_kind = "exhausted_path"
                deltas.append(
                    PlanExecutionDelta(
                        delta_id=_new_delta_id("monitor-decision"),
                        source="monitor",
                        kind=repair_kind,
                        summary=reason[:240] or "Monitor requested plan repair.",
                        evidence={"decisionAction": action},
                        consequence="medium",
                    )
                )

        return deltas
    except Exception:  # noqa: BLE001
        return []
