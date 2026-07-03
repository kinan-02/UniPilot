"""Tests for workflow pre-commit validation phase."""

from __future__ import annotations

import json

import pytest

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.workflow.validate import validate_committed_plan
from app.services.academic_graph_engine import AcademicGraphEngine


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
        }
    ]
    (raw / "courses_2025_201.json").write_text(json.dumps(courses), encoding="utf-8")
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_validate_committed_plan_accepts_feasible_plan(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(goal="plan", user_context={"completed_courses": []}, engine=engine)

    ok, violations, refs = validate_committed_plan(
        blackboard=board,
        course_ids=["00940139"],
    )

    assert ok is True
    assert violations == []
    assert "effector:validator:pre_commit_validated" in refs


def test_validate_committed_plan_rejects_unknown_course(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(goal="plan", user_context={"completed_courses": []}, engine=engine)

    ok, violations, _refs = validate_committed_plan(
        blackboard=board,
        course_ids=["99999999"],
    )

    assert ok is False
    assert violations


def test_validate_committed_plan_rejects_credit_overload(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="plan",
        user_context={
            "completed_courses": [],
            "preferences": {"maxCreditsPerSemester": 2},
        },
        engine=engine,
    )

    ok, violations, _refs = validate_committed_plan(
        blackboard=board,
        course_ids=["00940139"],
    )

    assert ok is False
    assert any("Credit overload" in item or "credits" in item.lower() for item in violations)
