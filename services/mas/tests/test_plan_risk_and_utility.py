"""Unit tests for plan risk and utility scoring."""

from __future__ import annotations

import pytest

from app.agents.risk_sentinel import RiskSentinelAgent
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.orchestrator.utility import score_plan
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.plan_risk import evaluate_credit_overload, resolve_max_credits


def _build_engine(tmp_path, *, credits_by_course: dict[str, str] | None = None) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    credits_by_course = credits_by_course or {}

    courses = [
        {
            "general": {
                "מספר מקצוע": "00940139",
                "שם מקצוע": "Intro Stats",
                "מקצועות קדם": "",
                "נקודות": credits_by_course.get("00940139", "3"),
            },
            "schedule": [],
        },
        {
            "general": {
                "מספר מקצוע": "0940345",
                "שם מקצוע": "Discrete Math",
                "מקצועות קדם": "00940139",
                "נקודות": credits_by_course.get("0940345", "4"),
            },
            "schedule": [],
        },
    ]
    import json

    (raw / "courses_2025_201.json").write_text(json.dumps(courses), encoding="utf-8")
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_resolve_max_credits_prefers_profile_preferences() -> None:
    assert resolve_max_credits({"preferences": {"maxCreditsPerSemester": 12}}) == 12.0
    assert resolve_max_credits({"constraints": {"maxCredits": 15}}) == 15.0


def test_evaluate_credit_overload_flags_excess_credits(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    is_safe, evidence, _refs = evaluate_credit_overload(
        engine=engine,
        course_ids=["00940139", "0940345"],
        max_credits=5,
    )

    assert is_safe is False
    assert evidence["totalCredits"] == 7.0
    assert evidence["excessCredits"] == 2.0


def test_score_plan_returns_weighted_breakdown(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    proposal = PlanProposal(course_ids=["00940139"], semester_filename="courses_2025_201.json")
    utility, breakdown = score_plan(
        proposal=proposal,
        engine=engine,
        user_context={"completed_courses": [], "preferences": {"maxCreditsPerSemester": 18}},
    )

    assert utility > 0
    assert breakdown["courseCount"] == 1
    assert "components" in breakdown


@pytest.mark.asyncio
async def test_risk_sentinel_vetoes_credit_overload(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="overload plan",
        user_context={"completed_courses": ["00940139"], "preferences": {"maxCreditsPerSemester": 3}},
        engine=engine,
    )
    board.set_candidate(
        PlanProposal(course_ids=["00940139", "0940345"], semester_filename="courses_2025_201.json")
    )

    turn = await RiskSentinelAgent().run(board)

    assert turn.action == "veto"
    assert turn.payload["riskType"] == "credit_overload"
    assert turn.payload["reasoningTrace"]["kind"] == "risk_review"
    assert turn.payload["reasoningTrace"]["violationCount"] >= 1
