"""Tests for semester resolution using profile plan code."""

from __future__ import annotations

from pathlib import Path

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.planner_support import resolve_semester_for_goal
from app.services.semester_catalog import discover_semester_catalogs


def test_resolve_semester_for_goal_uses_profile_plan_code_when_goal_unspecified(tmp_path: Path) -> None:
    raw_dir = tmp_path / "technion"
    wiki_dir = tmp_path / "wiki"
    raw_dir.mkdir()
    wiki_dir.mkdir()
    for name in ("courses_2025_200.json", "courses_2025_201.json", "courses_2025_202.json"):
        (raw_dir / name).write_text("[]", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_wiki(str(wiki_dir))
    engine.discover_semesters(str(raw_dir))
    engine.set_active_semester("courses_2025_201.json", str(raw_dir))
    engine.build_graph()

    semester, references = resolve_semester_for_goal(
        "Help me plan next semester",
        engine,
        str(raw_dir),
        profile_plan_semester_code="2025-1",
    )

    assert semester is not None
    assert semester.filename == "courses_2025_200.json"
    assert any(ref.startswith("semester:profile_plan_code=") for ref in references)


def test_resolve_semester_for_goal_prefers_explicit_goal_semester_over_profile(tmp_path: Path) -> None:
    raw_dir = tmp_path / "technion"
    raw_dir.mkdir()
    for name in ("courses_2025_200.json", "courses_2025_201.json", "courses_2025_202.json"):
        (raw_dir / name).write_text("[]", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.discover_semesters(str(raw_dir))
    engine.set_active_semester("courses_2025_200.json", str(raw_dir))
    engine.build_graph()

    semester, _references = resolve_semester_for_goal(
        "Plan courses for Spring 2026 semester",
        engine,
        str(raw_dir),
        profile_plan_semester_code="2025-1",
    )

    assert semester is not None
    assert semester.filename == "courses_2025_201.json"
