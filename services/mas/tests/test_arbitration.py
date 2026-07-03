"""Unit tests for multi-candidate arbitration."""

from __future__ import annotations

import json

from app.orchestrator.blackboard import Blackboard
from app.orchestrator.types import PlanProposal
from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.arbitration import arbitrate_candidates, feasible_candidates


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


def test_feasible_candidates_filters_ineligible_plan(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(goal="plan", engine=engine, user_context={"completed_courses": []})
    proposals = [
        PlanProposal(course_ids=["0940345"], variant="invalid"),
        PlanProposal(course_ids=["00940139"], variant="primary"),
    ]

    survivors = feasible_candidates(board, proposals)

    assert len(survivors) == 1
    assert survivors[0].course_ids == ["00940139"]


def test_arbitrate_candidates_prefers_feasible_variant(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    board = Blackboard(goal="plan", engine=engine, user_context={"completed_courses": []})
    proposals = [
        PlanProposal(course_ids=["00940139"], variant="primary"),
        PlanProposal(course_ids=["00940139", "0940345"], variant="alternate_progress"),
    ]

    chosen, result = arbitrate_candidates(board, proposals)

    assert chosen is not None
    assert chosen.variant == "primary"
    assert result.considered_variants == ["primary"]


def test_arbitrate_candidates_uses_per_variant_soft_scores(tmp_path) -> None:
    import asyncio

    engine = _build_engine(tmp_path)
    board = Blackboard(
        goal="plan",
        engine=engine,
        user_context={"completed_courses": ["00940139"], "constraints": {"maxCredits": 6}},
    )
    primary = PlanProposal(course_ids=["00940139"], variant="primary")
    overloaded = PlanProposal(course_ids=["00940139", "0940345"], variant="alternate_progress")
    from app.services.variant_evaluation import evaluate_all_variants

    evaluations = asyncio.run(evaluate_all_variants(board, [primary, overloaded]))
    assert evaluations[0].hard_ok is True
    assert evaluations[1].hard_ok is False

    chosen, result = arbitrate_candidates(
        board,
        [primary, overloaded],
        variant_evaluations=evaluations,
    )

    assert chosen is not None
    assert chosen.variant == "primary"
    assert result.considered_variants == ["primary"]
