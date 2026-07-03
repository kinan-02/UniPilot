"""Tests for MAS effector gateway."""

from __future__ import annotations

import json

import pytest

from app.effectors.gateway import MasEffectorGateway
from app.orchestrator.blackboard import Blackboard
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


def test_prefix_refs_keeps_existing_effector_markers() -> None:
    from app.effectors.gateway import _prefix_refs

    refs = _prefix_refs(["effector:catalog:already"], "catalog")
    assert refs == ["effector:catalog:already"]


def test_validate_catalog_plan_prefixes_references(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    gateway = MasEffectorGateway()

    ok, violations, refs = gateway.validate_catalog_plan(
        engine=engine,
        course_ids=["00940139"],
        completed_courses=[],
    )

    assert ok is True
    assert violations == []
    assert refs
    assert refs[0].startswith("effector:catalog:")


def test_evaluate_hard_constraints_prefixes_references(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    gateway = MasEffectorGateway()

    result = gateway.evaluate_hard_constraints(
        course_ids=["00940139"],
        engine=engine,
        completed_courses=[],
        user_context={},
    )

    assert result.ok is True
    assert any(ref.startswith("effector:") for ref in result.references)


def test_validate_committed_plan_uses_gateway_provenance(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    gateway = MasEffectorGateway()
    board = Blackboard(goal="plan", user_context={"completed_courses": []}, engine=engine)

    ok, violations, refs = gateway.validate_committed_plan(
        blackboard=board,
        course_ids=["00940139"],
    )

    assert ok is True
    assert violations == []
    assert "effector:validator:pre_commit_validated" in refs


@pytest.mark.asyncio
async def test_fetch_academic_risk_preview_caches_on_blackboard(monkeypatch) -> None:
    gateway = MasEffectorGateway()
    board = Blackboard(
        goal="plan",
        user_context={"user_id": "user-1", "plan_semester_code": "2025-1"},
    )

    async def _fake_fetch(**_kwargs):
        return {"probation": {"pressured": False}}

    monkeypatch.setattr(
        "app.services.academic_risk_cache.fetch_academic_risk_preview",
        _fake_fetch,
    )

    first = await gateway.fetch_academic_risk_preview(blackboard=board, course_ids=["00940139"])
    second = await gateway.fetch_academic_risk_preview(blackboard=board, course_ids=["00940139"])

    assert first == {"probation": {"pressured": False}}
    assert second == first


def test_list_eligible_catalog_courses_delegates(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    gateway = MasEffectorGateway()
    courses = gateway.list_eligible_catalog_courses(engine=engine, completed_courses=[])
    assert courses == ["00940139"]


def test_validate_committed_plan_requires_engine() -> None:
    gateway = MasEffectorGateway()
    board = Blackboard(goal="plan", user_context={})

    ok, violations, refs = gateway.validate_committed_plan(
        blackboard=board,
        course_ids=["00940139"],
    )

    assert ok is False
    assert violations
    assert refs == []


@pytest.mark.asyncio
async def test_fetch_graduation_progress_delegates(monkeypatch) -> None:
    gateway = MasEffectorGateway()

    async def _fake_fetch(**_kwargs):
        return {"completedCredits": 40}

    monkeypatch.setattr(
        "app.effectors.gateway.fetch_graduation_progress_for_user",
        _fake_fetch,
    )

    result = await gateway.fetch_graduation_progress(user_id="user-1")
    assert result == {"completedCredits": 40}


@pytest.mark.asyncio
async def test_preview_graduation_progress_delegates(monkeypatch) -> None:
    gateway = MasEffectorGateway()

    async def _fake_preview(**_kwargs):
        return {"completedCredits": 43.5}

    monkeypatch.setattr(
        "app.effectors.gateway.preview_graduation_progress_for_user",
        _fake_preview,
    )

    result = await gateway.preview_graduation_progress(
        user_id="user-1",
        additional_course_numbers=["00140008"],
    )
    assert result == {"completedCredits": 43.5}
