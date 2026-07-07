"""Deterministic evidence extraction for synthesis (Phase 21)."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.synthesis.schemas import EvidenceItem

_CLAIM_MAX = 240


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _claim(text: str) -> str:
    cleaned = (text or "").strip()
    return cleaned[:_CLAIM_MAX] if cleaned else "unspecified"


def _cap(items: list[EvidenceItem], limit: int) -> list[EvidenceItem]:
    return items[: max(0, limit)]


def evidence_from_live_response_summary(summary: dict[str, Any]) -> list[EvidenceItem]:
    if not isinstance(summary, dict) or not summary:
        return []
    preview = _claim(str(summary.get("textPreview") or ""))
    if not preview or preview == "unspecified":
        return []
    return [
        EvidenceItem(
            id=_new_id("workflow"),
            source_type="deterministic_workflow",
            source_name=str(summary.get("workflowName") or "live_workflow"),
            claim=preview,
            trust_level="authoritative",
            confidence=float(summary.get("confidence") or 0.9),
            provenance="deterministic",
            metadata={
                "blockCount": summary.get("blockCount"),
                "warningCount": summary.get("warningCount"),
                "topic": "live_response",
            },
        )
    ]


def evidence_from_specialist_summaries(items: list[dict[str, Any]]) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        claim = _claim(str(item.get("decisionSummary") or item.get("answerPreview") or item.get("summary") or ""))
        if claim == "unspecified":
            continue
        evidence.append(
            EvidenceItem(
                id=_new_id(f"specialist{index}"),
                source_type="specialist_agent",
                source_name=str(item.get("agentName") or item.get("specialistAgentName") or "specialist"),
                claim=claim,
                trust_level="medium",
                confidence=float(item.get("confidence") or 0.7),
                provenance="diagnostic",
                metadata={"topic": str(item.get("topic") or "specialist_output"), "status": item.get("status")},
            )
        )
    return evidence


def evidence_from_dynamic_agent_summaries(items: list[dict[str, Any]]) -> list[EvidenceItem]:
    evidence: list[EvidenceItem] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        claim = _claim(str(item.get("decisionSummary") or item.get("summary") or item.get("agentName") or ""))
        if claim == "unspecified":
            continue
        evidence.append(
            EvidenceItem(
                id=_new_id(f"dynamic{index}"),
                source_type="dynamic_agent",
                source_name=str(item.get("agentName") or "dynamic_agent"),
                claim=claim,
                trust_level="medium",
                confidence=float(item.get("confidence") or 0.65),
                provenance="diagnostic",
                metadata={"topic": "dynamic_agent_output", "status": item.get("status")},
            )
        )
    return evidence


def evidence_from_clarification(summary: dict[str, Any]) -> list[EvidenceItem]:
    if not isinstance(summary, dict):
        return []
    evidence: list[EvidenceItem] = []
    state = summary.get("clarificationState") if isinstance(summary.get("clarificationState"), dict) else {}
    effective = summary.get("effectiveClarificationContext")
    if isinstance(effective, dict):
        for index, answer in enumerate(effective.get("confirmedClarifications") or []):
            if not isinstance(answer, dict):
                continue
            value = _claim(str(answer.get("value") or ""))
            if value == "unspecified":
                continue
            provenance = str(answer.get("provenance") or "confirmed")
            evidence.append(
                EvidenceItem(
                    id=_new_id(f"clar{index}"),
                    source_type="confirmed_user_clarification" if provenance == "confirmed" else "assumed_user_preference",
                    source_name="clarification",
                    claim=value,
                    trust_level="high" if provenance == "confirmed" else "low",
                    confidence=float(answer.get("confidence") or (1.0 if provenance == "confirmed" else 0.5)),
                    provenance=provenance if provenance in {"confirmed", "assumed"} else "unknown",  # type: ignore[arg-type]
                    metadata={"topic": str(answer.get("topic") or "preference")},
                )
            )
    if state.get("provenance") and not evidence:
        for index, prov in enumerate(state.get("provenance") or []):
            evidence.append(
                EvidenceItem(
                    id=_new_id(f"clarstate{index}"),
                    source_type="assumed_user_preference",
                    source_name="clarification_state",
                    claim=_claim(f"Clarification provenance: {prov}"),
                    trust_level="low",
                    confidence=0.5,
                    provenance="assumed",
                    metadata={"topic": "clarification_provenance"},
                )
            )
    return evidence


def evidence_from_monitor(summary: dict[str, Any]) -> list[EvidenceItem]:
    if not isinstance(summary, dict) or not summary:
        return []
    evidence: list[EvidenceItem] = []
    decision = summary.get("decision") if isinstance(summary.get("decision"), dict) else {}
    action = str(decision.get("action") or "")
    if action == "abort_safely":
        evidence.append(
            EvidenceItem(
                id=_new_id("monitor"),
                source_type="monitor",
                source_name="monitor",
                claim="Monitor requested safe abort due to unsafe output.",
                trust_level="authoritative",
                confidence=0.95,
                provenance="deterministic",
                supports_final_answer=False,
                metadata={"topic": "unsafe_output", "signal": "unsafe_output"},
            )
        )
    for index, signal in enumerate(summary.get("signals") or []):
        if not isinstance(signal, dict):
            continue
        kind = str(signal.get("kind") or "")
        if kind in {"unsafe_output", "goal_drift", "missing_context"}:
            evidence.append(
                EvidenceItem(
                    id=_new_id(f"mon{index}"),
                    source_type="monitor",
                    source_name="monitor",
                    claim=_claim(f"Monitor signal: {kind}"),
                    trust_level="high",
                    confidence=0.85,
                    provenance="deterministic",
                    supports_final_answer=kind != "unsafe_output",
                    metadata={"topic": kind, "signal": kind},
                )
            )
    return evidence


def evidence_from_plan_repair(summary: dict[str, Any]) -> list[EvidenceItem]:
    if not isinstance(summary, dict) or not summary:
        return []
    mode = str(summary.get("modeUsed") or "")
    status = str(summary.get("status") or "")
    if not mode and not status:
        return []
    return [
        EvidenceItem(
            id=_new_id("repair"),
            source_type="plan_repair",
            source_name="plan_repair",
            claim=_claim(f"Plan repair status={status} mode={mode}"),
            trust_level="low",
            confidence=0.4,
            provenance="diagnostic",
            supports_final_answer=False,
            metadata={"topic": "plan_repair", "modeUsed": mode, "status": status},
        )
    ]


def build_evidence_items(
    *,
    live_response_summary: dict[str, Any],
    specialist_summaries: list[dict[str, Any]],
    dynamic_agent_summaries: list[dict[str, Any]],
    clarification_bundle: dict[str, Any],
    monitor_summary: dict[str, Any],
    plan_repair_summary: dict[str, Any],
    max_items: int,
) -> list[EvidenceItem]:
    items: list[EvidenceItem] = []
    items.extend(evidence_from_live_response_summary(live_response_summary))
    items.extend(evidence_from_specialist_summaries(specialist_summaries))
    items.extend(evidence_from_dynamic_agent_summaries(dynamic_agent_summaries))
    items.extend(evidence_from_clarification(clarification_bundle))
    items.extend(evidence_from_monitor(monitor_summary))
    items.extend(evidence_from_plan_repair(plan_repair_summary))
    return _cap(items, max_items)
