"""Build compact SynthesisInput from post-context metadata (Phase 21)."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.synthesis.evidence import build_evidence_items
from app.agent.synthesis.schemas import SynthesisInput
from app.config import Settings


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _safe_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _specialist_summaries_from_metadata(supervisor_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    specialist_validation = _safe_dict(supervisor_metadata.get("specialistValidation"))
    summaries: list[dict[str, Any]] = []
    for comparison in _safe_list(specialist_validation.get("comparisons")):
        summaries.append(
            {
                "agentName": comparison.get("specialistAgentName"),
                "topic": comparison.get("workflowName"),
                "status": "comparable" if comparison.get("comparable") else "not_comparable",
                "decisionSummary": (
                    f"Specialist comparison safeMatch={comparison.get('safeMatch')} "
                    f"comparable={comparison.get('comparable')}"
                ),
            }
        )
    return summaries


def _dynamic_agent_summaries_from_metadata(supervisor_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    dynamic = _safe_dict(supervisor_metadata.get("dynamicAgents"))
    summaries: list[dict[str, Any]] = []
    for run in _safe_list(dynamic.get("agents")):
        summaries.append(
            {
                "agentName": run.get("agentName") or run.get("specName"),
                "status": run.get("status"),
                "summary": run.get("decisionSummary") or run.get("summary"),
                "confidence": run.get("confidence"),
            }
        )
    return summaries


def build_synthesis_input(
    *,
    user_goal: str | None,
    normalized_request: str | None,
    live_response_summary: dict[str, Any],
    retrieval_metadata: dict[str, Any],
    supervisor_metadata: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> SynthesisInput:
    """Collect compact summaries only — never raw context, blocks, or payloads."""
    try:
        return _build(
            user_goal=user_goal,
            normalized_request=normalized_request,
            live_response_summary=live_response_summary,
            retrieval_metadata=retrieval_metadata,
            supervisor_metadata=supervisor_metadata,
            settings=settings,
        )
    except Exception:  # noqa: BLE001
        return SynthesisInput(
            synthesis_id=f"syn-{uuid.uuid4().hex[:12]}",
            user_goal=user_goal,
            normalized_request=normalized_request,
            constraints={"inputBuilderError": True},
        )


def _build(
    *,
    user_goal: str | None,
    normalized_request: str | None,
    live_response_summary: dict[str, Any],
    retrieval_metadata: dict[str, Any],
    supervisor_metadata: dict[str, Any] | None,
    settings: Settings | None,
) -> SynthesisInput:
    meta = _safe_dict(retrieval_metadata)
    sup = _safe_dict(supervisor_metadata)
    merged = {**meta, **sup}

    workflow_summary = {
        "workflowName": live_response_summary.get("workflowName"),
        "textPreviewLength": len(str(live_response_summary.get("textPreview") or "")),
        "blockCount": live_response_summary.get("blockCount"),
        "warningCount": live_response_summary.get("warningCount"),
    }

    planner = _safe_dict(merged.get("plannerDiagnostics"))
    planner_dynamic = _safe_dict(planner.get("plannerDynamicAgents"))
    planner_dynamic_summary = {
        "status": planner_dynamic.get("status"),
        "specsGenerated": planner_dynamic.get("specsGenerated"),
        "specsValidated": planner_dynamic.get("specsValidated"),
        "specsExecuted": planner_dynamic.get("specsExecuted"),
    }

    clarification_summary = {
        "clarificationDiagnostics": _safe_dict(merged.get("clarificationDiagnostics")),
        "clarificationState": _safe_dict(merged.get("clarificationState")),
        "effectiveClarificationContext": _safe_dict(merged.get("effectiveClarificationContext")),
    }

    max_items = 12
    if settings is not None:
        max_items = max(1, int(settings.agent_synthesis_max_evidence_items))

    specialist_summaries = _specialist_summaries_from_metadata(merged)
    dynamic_summaries = _dynamic_agent_summaries_from_metadata(merged)

    evidence_items = build_evidence_items(
        live_response_summary=_safe_dict(live_response_summary),
        specialist_summaries=specialist_summaries,
        dynamic_agent_summaries=dynamic_summaries,
        clarification_bundle=clarification_summary,
        monitor_summary=_safe_dict(merged.get("monitorDiagnostics")),
        plan_repair_summary=_safe_dict(merged.get("planRepairDiagnostics")),
        max_items=max_items,
    )

    return SynthesisInput(
        synthesis_id=f"syn-{uuid.uuid4().hex[:12]}",
        user_goal=user_goal,
        normalized_request=normalized_request,
        live_response_summary=_safe_dict(live_response_summary),
        workflow_summary=workflow_summary,
        specialist_summaries=specialist_summaries,
        dynamic_agent_summaries=dynamic_summaries,
        monitor_summary=_safe_dict(merged.get("monitorDiagnostics")),
        clarification_summary=clarification_summary,
        plan_repair_summary=_safe_dict(merged.get("planRepairDiagnostics")),
        planner_dynamic_agents_summary=planner_dynamic_summary,
        evidence_items=evidence_items,
        constraints={"maxEvidenceItems": max_items},
    )
