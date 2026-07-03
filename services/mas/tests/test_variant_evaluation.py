"""Unit tests for per-variant soft evaluation."""

from __future__ import annotations

import json

import pytest

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.variant_evaluation import evaluate_all_variants


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


@pytest.mark.asyncio
async def test_evaluate_all_variants_scores_each_plan(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="plan",
        engine=engine,
        user_context={"constraints": {"avoidDays": ["שישי"]}},
    )
    proposals = [
        PlanProposal(course_ids=["00940139"], variant="primary"),
        PlanProposal(course_ids=[], variant="empty"),
    ]

    evaluations = await evaluate_all_variants(board, proposals)

    assert len(evaluations) == 2
    assert evaluations[0].variant == "primary"
    assert evaluations[0].hard_ok is True
    assert evaluations[0].preference_report.critiques
    assert evaluations[1].hard_ok is False
