"""Unit tests for Student Advocate and preference support."""

from __future__ import annotations

import json

import pytest

from app.agents.student_advocate import StudentAdvocateAgent
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.preference_support import evaluate_soft_preferences


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    courses = [
        {
            "general": {
                "מספר מקצוע": "00940139",
                "שם מקצוע": "Intro Stats",
                "מקצועות קדם": "",
                "נקודות": "3",
            },
            "schedule": [
                {
                    "קבוצה": 11,
                    "סוג": "הרצאה",
                    "יום": "שישי",
                    "שעה": "10:30 - 12:30",
                }
            ],
        }
    ]
    (raw / "courses_2025_201.json").write_text(json.dumps(courses), encoding="utf-8")
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_evaluate_soft_preferences_flags_avoided_day(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    critiques, references = evaluate_soft_preferences(
        engine=engine,
        course_ids=["00940139"],
        user_context={"constraints": {"avoidDays": ["שישי"]}},
    )

    assert critiques
    assert critiques[0]["type"] == "day_preference_conflict"
    assert "preferences:avoidDays=שישי" in references


def test_evaluate_soft_preferences_flags_below_min_credits(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    critiques, _references = evaluate_soft_preferences(
        engine=engine,
        course_ids=["00940139"],
        user_context={"constraints": {"minCredits": 10}},
    )

    assert any(item["type"] == "below_min_credits" for item in critiques)


@pytest.mark.asyncio
async def test_student_advocate_never_vetoes(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="plan",
        user_context={"constraints": {"avoidDays": ["שישי"]}},
        engine=engine,
    )
    board.set_candidate(
        PlanProposal(course_ids=["00940139"], semester_filename="courses_2025_201.json")
    )

    turn = await StudentAdvocateAgent().run(board)

    assert turn.action == "critique"
    assert turn.action != "veto"
    assert len(turn.payload["critiques"]) == 1
    assert turn.payload["reasoningTrace"]["kind"] == "preference_review"
    assert turn.payload["reasoningTrace"]["critiqueCount"] == 1
