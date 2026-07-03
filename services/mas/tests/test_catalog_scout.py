"""Unit tests for Catalog Scout agent."""

from __future__ import annotations

import json

import pytest

from app.agents.catalog_scout import CatalogScoutAgent
from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
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


@pytest.mark.asyncio
async def test_catalog_scout_veto_includes_feasibility_trace(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="plan without prereq",
        user_context={"completed_courses": []},
        engine=engine,
    )
    board.set_candidate(
        PlanProposal(course_ids=["0940345"], semester_filename="courses_2025_201.json")
    )

    turn = await CatalogScoutAgent().run(board)

    assert turn.action == "veto"
    assert turn.payload["reasoningTrace"]["kind"] == "feasibility_review"
    assert turn.payload["reasoningTrace"]["approved"] is False


@pytest.mark.asyncio
async def test_catalog_scout_approval_includes_feasibility_trace(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="valid plan",
        user_context={"completed_courses": ["00940139"]},
        engine=engine,
    )
    board.set_candidate(
        PlanProposal(course_ids=["0940345"], semester_filename="courses_2025_201.json")
    )

    turn = await CatalogScoutAgent().run(board)

    assert turn.action == "critique"
    assert turn.payload["reasoningTrace"]["approved"] is True
