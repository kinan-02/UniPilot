"""Unit tests for synthesis conflict detection (Phase 21)."""

from __future__ import annotations

from app.agent.synthesis.conflict_detection import detect_synthesis_conflicts
from app.agent.synthesis.schemas import EvidenceItem


def _workflow() -> EvidenceItem:
    return EvidenceItem(
        id="wf",
        source_type="deterministic_workflow",
        source_name="wf",
        claim="Complete",
        trust_level="authoritative",
        metadata={"topic": "graduation", "status": "complete"},
    )


def _specialist() -> EvidenceItem:
    return EvidenceItem(
        id="sp",
        source_type="specialist_agent",
        source_name="graduation_progress_agent",
        claim="Incomplete",
        trust_level="medium",
        metadata={"topic": "graduation", "status": "incomplete"},
    )


def test_specialist_conflict_with_workflow_detected() -> None:
    conflicts = detect_synthesis_conflicts([_workflow(), _specialist()])
    assert any("Specialist" in c.summary for c in conflicts)


def test_dynamic_agent_conflict_with_workflow_detected() -> None:
    dynamic = EvidenceItem(
        id="dyn",
        source_type="dynamic_agent",
        source_name="dyn",
        claim="Different",
        trust_level="medium",
    )
    conflicts = detect_synthesis_conflicts([_workflow(), dynamic])
    assert any("Dynamic-agent" in c.summary for c in conflicts)


def test_confirmed_clarification_conflict_with_assumed_preference_detected() -> None:
    confirmed = EvidenceItem(
        id="c",
        source_type="confirmed_user_clarification",
        source_name="clar",
        claim="Track A",
        trust_level="high",
    )
    assumed = EvidenceItem(
        id="a",
        source_type="assumed_user_preference",
        source_name="clar",
        claim="Track B",
        trust_level="low",
        provenance="assumed",
    )
    conflicts = detect_synthesis_conflicts([confirmed, assumed])
    assert conflicts


def test_monitor_unsafe_output_creates_conflict() -> None:
    conflicts = detect_synthesis_conflicts([], monitor_summary={"decision": {"action": "abort_safely"}})
    assert any(c.severity == "error" for c in conflicts)


def test_missing_context_with_candidate_ready_creates_conflict() -> None:
    missing = EvidenceItem(
        id="m",
        source_type="monitor",
        source_name="monitor",
        claim="missing",
        trust_level="high",
        metadata={"signal": "missing_context", "topic": "missing_context"},
    )
    conflicts = detect_synthesis_conflicts([missing])
    assert conflicts


def test_plan_repair_regenerate_vs_candidate_ready_creates_conflict() -> None:
    conflicts = detect_synthesis_conflicts([], plan_repair_summary={"modeUsed": "regenerate"})
    assert conflicts


def test_no_conflict_for_consistent_evidence() -> None:
    only = EvidenceItem(
        id="only",
        source_type="deterministic_workflow",
        source_name="wf",
        claim="ok",
        trust_level="authoritative",
    )
    assert detect_synthesis_conflicts([only]) == []


def test_malformed_evidence_never_raises() -> None:
    detect_synthesis_conflicts(
        [EvidenceItem(id="x", source_type="unknown", source_name="x", claim="", trust_level="low")]
    )
