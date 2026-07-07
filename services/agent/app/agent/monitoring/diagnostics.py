"""Compact monitor diagnostics metadata (Phase 16)."""

from __future__ import annotations

from typing import Any

from app.agent.monitoring.schemas import MonitorOutput

_MAX_SIGNALS = 8
_MAX_WARNINGS = 8


def build_monitor_metadata(output: MonitorOutput) -> dict[str, Any]:
    """Compact dict for `retrievalMetadata.monitorDiagnostics`."""
    return {
        "status": output.status,
        "planId": output.plan_id,
        "signalCount": len(output.signals),
        "signals": [
            {
                "kind": signal.kind,
                "severity": signal.severity,
            }
            for signal in output.signals[:_MAX_SIGNALS]
        ],
        "decision": {
            "action": output.decision.action,
            "repairScope": output.decision.repair_scope,
            "clarificationNeeded": output.decision.clarification_needed,
            "reason": output.decision.reason,
        },
        "checkedAssumptionCount": output.checked_assumption_count,
        "checkedExpectationCount": output.checked_expectation_count,
        "warnings": list(output.warnings[:_MAX_WARNINGS]),
    }


def build_monitor_output_diagnostics(output: MonitorOutput) -> dict[str, Any]:
    """Internal diagnostics payload stored on `MonitorOutput.diagnostics`."""
    return {
        "decisionConfidence": output.decision.confidence,
        "divergenceKinds": list(output.decision.divergence_kinds),
        "affectedSubtaskCount": len(output.decision.affected_subtasks),
        "affectedAssumptionCount": len(output.decision.affected_assumptions),
    }
