"""Unit tests for unified hard constraint evaluation."""

from __future__ import annotations

import json

from app.orchestrator.artifacts import ViolationType
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.plan_hard_constraints import evaluate_hard_constraints


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
            "schedule": [],
        },
        {
            "general": {
                "מספר מקצוע": "0940345",
                "שם מקצוע": "Discrete Math",
                "מקצועות קדם": "00940139",
                "נקודות": "4",
            },
            "schedule": [],
        },
    ]
    (raw / "courses_2025_201.json").write_text(json.dumps(courses), encoding="utf-8")
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_hard_constraints_reject_prereq_violation(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    result = evaluate_hard_constraints(
        course_ids=["0940345"],
        engine=engine,
        completed_courses=[],
        user_context={},
    )

    assert result.ok is False
    assert result.veto_agent == "catalog_scout"
    assert any(item.type == ViolationType.PREREQ_MISSING for item in result.violations)


def test_hard_constraints_reject_credit_overload(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    result = evaluate_hard_constraints(
        course_ids=["00940139", "0940345"],
        engine=engine,
        completed_courses=["00940139"],
        user_context={"constraints": {"maxCredits": 3}},
    )

    assert result.ok is False
    assert result.veto_agent == "risk_sentinel"
    assert any(item.type == ViolationType.CREDIT_OVERLOAD for item in result.violations)
