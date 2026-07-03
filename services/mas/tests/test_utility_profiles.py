"""Tests for utility weight profiles."""

from __future__ import annotations

from app.orchestrator.utility import UTILITY_PROFILES, resolve_utility_weights


def test_resolve_utility_weights_defaults_to_balanced() -> None:
    weights = resolve_utility_weights({})
    assert weights == UTILITY_PROFILES["balanced"]


def test_resolve_utility_weights_honors_profile() -> None:
    weights = resolve_utility_weights({"constraints": {"utilityProfile": "risk_averse"}})
    assert weights["risk_penalty"] == UTILITY_PROFILES["risk_averse"]["risk_penalty"]


def test_utility_profiles_change_score_for_probation_pressure(tmp_path) -> None:
    from app.orchestrator.artifacts import RiskReport
    from app.orchestrator.types import PlanProposal
    from app.orchestrator.utility import score_plan
    from tests.test_orchestrator import _build_engine

    engine = _build_engine(tmp_path)
    proposal = PlanProposal(course_ids=["00940139"], semester_filename="courses_2025_201.json")
    risk_report = RiskReport(ok=True, evidence={"probation": {"pressured": True}})
    user_context = {
        "completed_courses": [],
        "preferences": {"maxCreditsPerSemester": 18},
    }

    _balanced_score, balanced = score_plan(
        proposal=proposal,
        engine=engine,
        user_context={**user_context, "constraints": {"utilityProfile": "balanced"}},
        risk_report=risk_report,
    )
    _risk_averse_score, risk_averse = score_plan(
        proposal=proposal,
        engine=engine,
        user_context={**user_context, "constraints": {"utilityProfile": "risk_averse"}},
        risk_report=risk_report,
    )

    assert balanced["utilityProfile"] == "balanced"
    assert risk_averse["utilityProfile"] == "risk_averse"
    assert balanced["utility"] != risk_averse["utility"]
