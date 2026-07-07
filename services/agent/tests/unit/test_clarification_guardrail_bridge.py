"""Tests for deterministic clarification guardrail bridge (Phase 26.1)."""

from __future__ import annotations

from app.agent.clarification.guardrail_bridge import (
    apply_clarification_guardrail,
    detect_semester_planning_clarification_need,
)


def test_detect_missing_preferences_for_next_semester_question() -> None:
    detection = detect_semester_planning_clarification_need(
        "What should I take next semester? I haven't decided anything yet."
    )
    assert detection is not None
    assert detection.kind == "missing_preferences"
    assert detection.consequence == "medium"


def test_detect_contradictory_preferences() -> None:
    detection = detect_semester_planning_clarification_need(
        "I want a light semester but also pack in 24 credits and two labs."
    )
    assert detection is not None
    assert detection.kind == "preference_conflict"
    assert detection.consequence == "high"


def test_apply_guardrail_sets_ask_user_action() -> None:
    replay_meta = {
        "clarificationDiagnostics": {
            "questions": [{"ambiguityType": "preference", "consequence": "medium"}]
        }
    }
    merged = apply_clarification_guardrail(
        user_message="What should I take next semester? I haven't decided anything yet.",
        replay_meta=replay_meta,
        enabled=True,
    )
    clar = merged["clarificationDiagnostics"]
    assert clar["action"] == "ask_user"
    assert clar["status"] == "question_ready"
    assert merged["clarificationGuardrail"]["kind"] == "missing_preferences"


def test_apply_guardrail_noop_when_disabled() -> None:
    replay_meta = {"clarificationDiagnostics": {"questions": []}}
    merged = apply_clarification_guardrail(
        user_message="What should I take next semester?",
        replay_meta=replay_meta,
        enabled=False,
    )
    assert merged == replay_meta


def test_real_world_fixtures_pass_after_guardrail_merge() -> None:
    from pathlib import Path

    from app.agent.evaluation.case_loader import load_eval_cases
    from app.agent.evaluation.gates_eval import build_observed_from_case, evaluate_case_result

    fixtures = Path(__file__).resolve().parents[1] / "fixtures" / "eval_cases_real_world_like"
    for case_id in (
        "real_world_like_next_semester_missing_prefs",
        "real_world_like_contradictory_preference",
    ):
        case = load_eval_cases(fixtures / f"{case_id}.json", strict=True)[0]
        replay_meta = apply_clarification_guardrail(
            user_message=case.user_message,
            replay_meta=dict(case.retrieval_metadata),
            enabled=True,
        )
        observed = build_observed_from_case(case, replay_observed=replay_meta)
        result = evaluate_case_result(case=case, observed=observed)
        assert "clarification_action_mismatch" not in result.failures, case_id

