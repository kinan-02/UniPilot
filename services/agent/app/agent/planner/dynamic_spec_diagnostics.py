"""Compact diagnostics for planner-emitted dynamic AgentSpecs (Phase 20)."""

from __future__ import annotations

from typing import Any

_MAX_REJECTION_REASONS = 8
_MAX_AGENTS = 8
_MAX_WARNINGS = 8


def build_planner_dynamic_agents_metadata(
    normalization_diagnostics: dict[str, Any] | None,
    *,
    executed_agents: list[dict[str, Any]] | None = None,
    dynamic_agents_metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build compact `retrievalMetadata.plannerDynamicAgents`. Never stores raw specs."""
    if not normalization_diagnostics:
        return None

    generated = int(normalization_diagnostics.get("specsGenerated") or 0)
    if generated == 0 and not executed_agents and not dynamic_agents_metadata:
        status = str(normalization_diagnostics.get("status") or "skipped")
        if status == "skipped":
            return None

    agents = list(normalization_diagnostics.get("agents") or [])[:_MAX_AGENTS]
    specs_executed = 0

    if dynamic_agents_metadata:
        specs_executed = int(dynamic_agents_metadata.get("agentCount") or 0)
        for summary in dynamic_agents_metadata.get("agents") or []:
            if not isinstance(summary, dict):
                continue
            spec_id = summary.get("specId")
            if not spec_id:
                continue
            matched = next((agent for agent in agents if agent.get("specId") == spec_id), None)
            if matched is not None:
                matched["status"] = summary.get("status", matched.get("status"))
                matched["confidence"] = summary.get("confidence", 0.0)
            else:
                agents.append(
                    {
                        "specId": spec_id,
                        "agentName": summary.get("agentName"),
                        "reasoningPattern": summary.get("reasoningPattern"),
                        "riskLevel": summary.get("riskLevel", "medium"),
                        "status": summary.get("status"),
                        "confidence": summary.get("confidence", 0.0),
                    }
                )

    if executed_agents:
        specs_executed = max(specs_executed, len(executed_agents))
        for summary in executed_agents[:_MAX_AGENTS]:
            if isinstance(summary, dict):
                spec_id = summary.get("specId")
                if spec_id and not any(a.get("specId") == spec_id for a in agents):
                    agents.append(summary)

    status = str(normalization_diagnostics.get("status") or "skipped")
    if specs_executed and status in {"skipped", "validated"}:
        status = "completed"

    return {
        "status": status,
        "specsGenerated": generated,
        "specsValidated": int(normalization_diagnostics.get("specsValidated") or 0),
        "specsRejected": int(normalization_diagnostics.get("specsRejected") or 0),
        "specsExecuted": specs_executed,
        "rejectionReasons": list(normalization_diagnostics.get("rejectionReasons") or [])[:_MAX_REJECTION_REASONS],
        "agents": agents[:_MAX_AGENTS],
        "warnings": list(normalization_diagnostics.get("warnings") or [])[:_MAX_WARNINGS],
    }


def merge_planner_dynamic_execution_metadata(
    planner_dynamic: dict[str, Any] | None,
    dynamic_agents_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Enrich planner dynamic diagnostics with supervisor execution summaries."""
    if planner_dynamic is None and dynamic_agents_metadata is None:
        return None
    return build_planner_dynamic_agents_metadata(
        planner_dynamic or {"status": "skipped", "specsGenerated": 0},
        dynamic_agents_metadata=dynamic_agents_metadata,
    )
