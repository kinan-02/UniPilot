"""Unit tests for runtime readiness schemas (Phase 25)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.agent.readiness.schemas import (
    RuntimeReadinessCandidateApproval,
    RuntimeReadinessGateDecision,
    RuntimeReadinessGateInput,
    RuntimeReadinessManifest,
    level_at_least,
)


def test_runtime_readiness_manifest_parses() -> None:
    manifest = RuntimeReadinessManifest.model_validate(
        {
            "schemaVersion": "1",
            "reviewedAt": "2026-07-06T00:00:00Z",
            "reviewedBy": "human",
            "candidates": [],
        }
    )
    assert manifest.schema_version == "1"


def test_runtime_readiness_candidate_approval_parses() -> None:
    candidate = RuntimeReadinessCandidateApproval.model_validate(
        {
            "candidateId": "synthesis_text_promotion.course_question_workflow",
            "level": "ready_for_limited_promotion",
            "approved": True,
            "scope": ["course_question_workflow"],
        }
    )
    assert candidate.approved is True


def test_runtime_readiness_gate_input_parses() -> None:
    gate_input = RuntimeReadinessGateInput(candidate_id="test")
    assert gate_input.required_level == "ready_for_limited_promotion"


def test_runtime_readiness_gate_decision_parses() -> None:
    decision = RuntimeReadinessGateDecision(candidate_id="test", allowed=False)
    assert decision.allowed is False


def test_level_ordering_works() -> None:
    assert level_at_least("ready_for_broader_promotion", "ready_for_limited_promotion")
    assert not level_at_least("ready_for_shadow", "ready_for_limited_promotion")


def test_forbidden_chain_of_thought_fields_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_field"):
        RuntimeReadinessManifest.model_validate(
            {"schemaVersion": "1", "chain_of_thought": "secret", "candidates": []}
        )
