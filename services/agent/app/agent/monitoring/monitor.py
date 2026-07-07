"""Plan execution monitor (Phase 16).

Deterministic, diagnostic-only control layer that compares expected plan
assumptions/subtask expectations against actual supervisor execution results
and emits divergence signals plus a replan/repair recommendation. Never
calls an LLM and never triggers real replanning in Phase 16.
"""

from __future__ import annotations

import logging
from typing import Any

from app.agent.monitoring.assumptions import build_assumptions_for_monitor
from app.agent.monitoring.diagnostics import build_monitor_metadata, build_monitor_output_diagnostics
from app.agent.monitoring.divergence import detect_divergence
from app.agent.monitoring.expectations import build_expectations_for_monitor
from app.agent.monitoring.replan_decision import decide_replan_action
from app.agent.monitoring.schemas import MonitorInput, MonitorOutput, ReplanDecision

logger = logging.getLogger(__name__)

_SKIPPED_DECISION = ReplanDecision(
    action="continue",
    reason="monitor_disabled",
    confidence=1.0,
    divergence_kinds=["none"],
    repair_scope="none",
)


def _normalize_subtask_records(records: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for record in records or []:
        if hasattr(record, "model_dump"):
            normalized.append(record.model_dump())
        elif isinstance(record, dict):
            normalized.append(dict(record))
    return normalized


def _normalize_supervisor_output(supervisor_output: dict[str, Any] | Any | None) -> dict[str, Any]:
    if supervisor_output is None:
        return {}
    if hasattr(supervisor_output, "model_dump"):
        return supervisor_output.model_dump()
    return dict(supervisor_output) if isinstance(supervisor_output, dict) else {}


def _derive_status(signals: list[Any], decision: ReplanDecision) -> str:
    kinds = {signal.kind for signal in signals}
    if decision.action == "abort_safely":
        return "failed"
    if decision.action not in {"continue"} or any(kind not in {"none", "promotion_blocked"} for kind in kinds):
        if any(signal.severity == "error" for signal in signals):
            return "diverged" if decision.action != "abort_safely" else "failed"
        return "passed_with_warnings" if kinds != {"none"} else "passed"
    if kinds == {"none"}:
        return "passed"
    if any(signal.severity == "warning" for signal in signals):
        return "passed_with_warnings"
    return "passed"


def monitor_plan_execution(
    input: MonitorInput,
    *,
    enabled: bool = True,
    dry_run: bool = True,
) -> MonitorOutput:
    """Compare expected vs actual execution and return diagnostic monitor output.

    Never raises.
    """
    warnings: list[str] = []
    if not enabled:
        return MonitorOutput(
            status="skipped",
            plan_id=input.plan_id,
            decision=_SKIPPED_DECISION,
            warnings=["monitor_disabled"],
        )

    if not dry_run:
        warnings.append("monitor_forced_dry_run")

    try:
        planner_output = dict(input.planner_output or {})
        supervisor_output = _normalize_supervisor_output(input.supervisor_output)
        subtask_records = input.subtask_records or _normalize_subtask_records(supervisor_output.get("subtask_records") or [])

        assumptions = build_assumptions_for_monitor(
            planner_output=planner_output,
            task_understanding=input.task_understanding,
            conversation_assumptions=input.conversation_assumptions,
            preset=input.assumptions,
        )
        expectations = build_expectations_for_monitor(
            planner_output=planner_output,
            preset=input.expectations,
        )

        normalized_input = input.model_copy(
            update={
                "planner_output": planner_output,
                "supervisor_output": supervisor_output,
                "subtask_records": subtask_records,
                "plan_id": input.plan_id or planner_output.get("plan_id"),
                "user_goal": input.user_goal or planner_output.get("user_goal"),
            }
        )

        signals = detect_divergence(normalized_input, assumptions, expectations)
        decision = decide_replan_action(signals, normalized_input)
        status = _derive_status(signals, decision)

        output = MonitorOutput(
            status=status,  # type: ignore[arg-type]
            plan_id=normalized_input.plan_id,
            signals=signals,
            decision=decision,
            checked_assumption_count=len(assumptions),
            checked_expectation_count=len(expectations),
            warnings=warnings,
            diagnostics=build_monitor_output_diagnostics(
                MonitorOutput(
                    status=status,  # type: ignore[arg-type]
                    plan_id=normalized_input.plan_id,
                    signals=signals,
                    decision=decision,
                    checked_assumption_count=len(assumptions),
                    checked_expectation_count=len(expectations),
                )
            ),
        )
        output.diagnostics["metadata"] = build_monitor_metadata(output)
        return output
    except Exception:  # noqa: BLE001 — monitor must never break a live turn
        logger.exception("monitor_plan_execution_failed")
        return MonitorOutput(
            status="failed",
            plan_id=input.plan_id,
            signals=[],
            decision=ReplanDecision(
                action="continue",
                reason="monitor_internal_failure",
                confidence=0.0,
                divergence_kinds=["none"],
            ),
            warnings=[*warnings, "monitor_internal_failure"],
        )


def build_monitor_input_from_shadow_context(
    *,
    planner_output: dict[str, Any] | None,
    shadow_run_output: Any | None,
    task_understanding: dict[str, Any] | None = None,
    conversation_assumptions: list[str] | None = None,
    latest_user_message: str | None = None,
    validation_metadata: dict[str, Any] | None = None,
    promotion_metadata: dict[str, Any] | None = None,
    specialist_validation_metadata: dict[str, Any] | None = None,
    dynamic_agent_metadata: dict[str, Any] | None = None,
) -> MonitorInput:
    supervisor_output = _normalize_supervisor_output(shadow_run_output)
    return MonitorInput(
        plan_id=(planner_output or {}).get("plan_id"),
        user_goal=(planner_output or {}).get("user_goal"),
        planner_output=dict(planner_output or {}),
        supervisor_output=supervisor_output,
        subtask_records=_normalize_subtask_records(supervisor_output.get("subtask_records") or []),
        task_understanding=dict(task_understanding or {}),
        conversation_assumptions=list(conversation_assumptions or []),
        latest_user_message=latest_user_message,
        validation_metadata=dict(validation_metadata or {}),
        promotion_metadata=dict(promotion_metadata or {}),
        specialist_validation_metadata=dict(specialist_validation_metadata or {}),
        dynamic_agent_metadata=dict(dynamic_agent_metadata or {}),
    )
