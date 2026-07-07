"""Unit tests for real-world case schemas (Phase 26)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.real_world_schemas import RealWorldCaseInput, assert_no_forbidden_import_keys


def test_real_world_case_input_parses() -> None:
    case = RealWorldCaseInput(
        anonymized_user_message="What electives remain?",
        tags=["graduation"],
    )
    assert case.source == "manual"


def test_reviewer_expected_outcome_accepted() -> None:
    case = RealWorldCaseInput(
        anonymized_user_message="Explain faculty electives",
        reviewer_expected_outcome={"expected_workflow": "requirement_explanation_workflow"},
    )
    assert case.reviewer_expected_outcome["expected_workflow"] == "requirement_explanation_workflow"


def test_defaults_are_safe() -> None:
    case = RealWorldCaseInput(anonymized_user_message="Safe anonymized message")
    assert case.anonymized_context == {}
    assert case.tags == []


def test_forbidden_chain_of_thought_fields_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_field"):
        RealWorldCaseInput.model_validate(
            {"anonymized_user_message": "x", "chain_of_thought": "hidden"}
        )


def test_raw_transcript_key_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_field"):
        RealWorldCaseInput.model_validate(
            {"anonymized_user_message": "x", "raw_transcript": [{"grade": 90}]}
        )


def test_assert_no_forbidden_import_keys_nested() -> None:
    with pytest.raises(ValueError, match="forbidden_import_keys"):
        assert_no_forbidden_import_keys({"anonymized_user_message": "x", "student_id": "123456789"})
