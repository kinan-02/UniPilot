"""Unit tests for real-world case importer (Phase 26)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.real_world_importer import convert_real_world_case_to_eval_case, import_real_world_cases
from app.agent.evaluation.real_world_schemas import RealWorldCaseInput
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload


def test_converts_real_world_input_to_eval_case() -> None:
    case = convert_real_world_case_to_eval_case(
        RealWorldCaseInput(
            anonymized_user_message="What are prerequisites for course B?",
            reviewer_expected_outcome={"expected_workflow": "course_question_workflow"},
            tags=["course_question"],
        ),
        case_id="real_world_001",
    )
    assert case.user_message.startswith("What are prerequisites")
    assert case.kind == "course_question"


def test_adds_real_world_like_tag() -> None:
    case = convert_real_world_case_to_eval_case(
        RealWorldCaseInput(anonymized_user_message="Hello"),
        case_id="rw_1",
    )
    assert "real_world_like" in case.tags


def test_adds_human_reviewed_tag_when_expected_outcome_exists() -> None:
    case = convert_real_world_case_to_eval_case(
        RealWorldCaseInput(
            anonymized_user_message="Hello",
            reviewer_expected_outcome={"expected_intent": "course_question"},
        ),
        case_id="rw_2",
    )
    assert "human_reviewed" in case.tags


def test_deterministic_case_ids_from_import() -> None:
    payload = RealWorldCaseInput(anonymized_user_message="Same message", tags=["course"])
    cases_a, _ = import_real_world_cases([payload], prefix="real_world")
    cases_b, _ = import_real_world_cases([payload], prefix="real_world")
    assert cases_a[0].id == cases_b[0].id


def test_generated_case_passes_eval_sanitizer() -> None:
    case = convert_real_world_case_to_eval_case(
        RealWorldCaseInput(anonymized_user_message="Safe message"),
        case_id="rw_safe",
    )
    assert_no_forbidden_eval_payload(case.model_dump())


def test_strict_mode_rejects_unsafe_identifiers() -> None:
    with pytest.raises(ValueError, match="unsafe_identifiers"):
        import_real_world_cases(
            [
                RealWorldCaseInput(
                    anonymized_user_message="Contact me at student@example.com for help",
                )
            ],
            strict=True,
        )


def test_dry_run_writes_nothing(tmp_path) -> None:
    cases, warnings = import_real_world_cases(
        [RealWorldCaseInput(anonymized_user_message="student@example.com")],
        strict=False,
    )
    assert cases
    assert warnings
    assert not list(tmp_path.glob("*.json"))
