"""Unit tests for synthesis evidence extraction (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.evidence import (
    build_evidence_items,
    evidence_from_clarification,
    evidence_from_dynamic_agent_summaries,
    evidence_from_live_response_summary,
    evidence_from_monitor,
    evidence_from_specialist_summaries,
)


def test_deterministic_workflow_evidence_gets_authoritative_trust() -> None:
    items = evidence_from_live_response_summary({"textPreview": "Need 3 credits.", "workflowName": "wf"})
    assert items[0].trust_level == "authoritative"


def test_confirmed_clarification_gets_high_trust() -> None:
    items = evidence_from_clarification(
        {
            "effectiveClarificationContext": {
                "confirmedClarifications": [{"value": "Track A", "provenance": "confirmed"}]
            }
        }
    )
    assert items[0].trust_level == "high"


def test_assumed_preference_gets_lower_trust() -> None:
    items = evidence_from_clarification(
        {
            "effectiveClarificationContext": {
                "confirmedClarifications": [{"value": "Maybe track B", "provenance": "assumed"}]
            }
        }
    )
    assert items[0].trust_level == "low"


def test_validated_specialist_evidence_gets_medium_trust() -> None:
    items = evidence_from_specialist_summaries([{"decisionSummary": "Specialist view", "status": "completed"}])
    assert items[0].trust_level == "medium"


def test_validated_dynamic_agent_evidence_gets_medium_trust() -> None:
    items = evidence_from_dynamic_agent_summaries([{"summary": "Dynamic insight", "status": "completed"}])
    assert items[0].trust_level == "medium"


def test_monitor_unsafe_signal_becomes_evidence() -> None:
    items = evidence_from_monitor({"decision": {"action": "abort_safely"}})
    assert items
    assert items[0].metadata.get("signal") == "unsafe_output"


def test_evidence_count_cap_enforced() -> None:
    items = build_evidence_items(
        live_response_summary={"textPreview": "live"},
        specialist_summaries=[{"decisionSummary": f"s{i}"} for i in range(10)],
        dynamic_agent_summaries=[{"summary": f"d{i}"} for i in range(10)],
        clarification_bundle={},
        monitor_summary={},
        plan_repair_summary={},
        max_items=3,
    )
    assert len(items) == 3


def test_raw_payloads_omitted() -> None:
    items = evidence_from_live_response_summary({"textPreview": "ok", "blocks": [{"type": "table"}]})
    assert "blocks" not in items[0].metadata
