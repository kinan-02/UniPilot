"""Unit tests for workflow finalize helpers."""

from __future__ import annotations

import json

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.orchestrator.workflow.finalize import record_best_candidate, relax_soft_constraints
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


def test_relax_soft_constraints_removes_negotiable_preferences() -> None:
    board = Blackboard(
        goal="plan",
        user_context={
            "constraints": {
                "avoidDays": ["שישי"],
                "preferredDaysOff": ["שישי"],
                "minCredits": 12,
                "maxCredits": 22,
            }
        },
    )

    relaxed = relax_soft_constraints(board)

    assert relaxed is True
    assert board.user_context["constraints"] == {"maxCredits": 22}
    assert board.relaxed_constraints


def test_record_best_candidate_tracks_highest_utility_plan(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    proposal = PlanProposal(variant="balanced", course_ids=["00940139"])
    board = Blackboard(
        goal="plan",
        user_context={"completed_courses": []},
        engine=engine,
        candidate_plan=proposal,
    )

    record_best_candidate(board)

    assert board.best_seen_plan == proposal
    assert board.best_seen_score > 0
    assert board.utility_breakdown is not None
