"""Tests for MAS session continuation metadata."""

from __future__ import annotations

from app.sessions.continuations import (
    build_session_lineage,
    merge_lineage_into_decision,
)


def test_build_session_lineage_for_second_opinion() -> None:
    lineage = build_session_lineage(
        {
            "constraints": {
                "utilityProfile": "risk_averse",
                "secondOpinionOf": "abc123",
            }
        }
    )
    assert lineage is not None
    assert lineage["kind"] == "second_opinion"
    assert lineage["sourceSessionId"] == "abc123"
    assert lineage["utilityProfile"] == "risk_averse"


def test_build_session_lineage_for_clarification_resume() -> None:
    lineage = build_session_lineage(
        {
            "clarifications": [{"text": "Plan light load"}],
            "priorTranscript": [{"agent_role": "goal_analyst"}],
        }
    )
    assert lineage is not None
    assert lineage["kind"] == "clarification_resume"
    assert lineage["clarificationCount"] == 1
    assert lineage["priorTranscriptTurns"] == 1


def test_merge_lineage_into_decision_without_lineage() -> None:
    decision = {"course_ids": ["00140008"]}
    assert merge_lineage_into_decision(decision, None) == decision


def test_build_session_lineage_returns_none_for_plain_session() -> None:
    assert build_session_lineage({"goal": "plan next semester"}) is None


def test_merge_lineage_into_decision() -> None:
    merged = merge_lineage_into_decision(
        {"course_ids": ["00140008"]},
        {"kind": "second_opinion", "sourceSessionId": "abc123"},
    )
    assert merged is not None
    assert merged["sessionLineage"]["kind"] == "second_opinion"
